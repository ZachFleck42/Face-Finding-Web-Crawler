import os
import psycopg2
import requests
import sys
import time
from bs4 import BeautifulSoup
from psycopg2 import sql
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from tasks import processImage
from urllib.parse import urlparse


# Create a queue of URLs to visit and collect data from.
# Each URL will also have a corresponding 'depth', or number of links removed from the original URL.
# Thus, the queue will be a list of tuples in the form (string URL, int Depth)
urls = []

# Store the initial URL as a global variable for reference across functions
INITIAL_URL = (sys.argv[1]).rstrip('/')

# Define a 'maximum depth', or how far removed from the main URL the program should explore
MAX_DEPTH = int(sys.argv[2])

# Create a list of already-visited links to prevent visiting the same page twice
visitedLinks = []


def tableExists(DbConnection, tableName):
    '''
    Accepts a database connection and a table name to check.
    If table exists in the databse, function returns True. Returns false otherwise.
    '''
    cur = DbConnection.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = '{0}'
        """.format(tableName.replace('\'', '\'\'')))
    if cur.fetchone()[0] == 1:
        cur.close()
        return True

    cur.close()
    return False


def initializeDb(tableName):
    '''
    Connects to a database and creates a fresh table with the name {tableName}.
    Closes connection afterwards and returns nothing.
    '''
    # Connect to PostgresSQL database and get a cursor
    conn = psycopg2.connect(host='postgres', database='faceCrawler', user='postgres', password='postgres')
    cur = conn.cursor()

    # If a table already exists for the website, delete it
    if tableExists(conn, tableName):
        cur.execute(sql.SQL("DROP TABLE {}")
                    .format(sql.Identifier(tableName)))

    # Create a new table for the website
    cur.execute(sql.SQL("CREATE TABLE {} (page_url VARCHAR, face_count INT)")
                .format(sql.Identifier(tableName)))

    # Commit changes and close the connection
    conn.commit()
    cur.close()
    conn.close()


def getLinks(pageResponse):
    '''
    Accepts a webpage in the form of a 'response object' from the Requests package.
    Returns a list of cleaned links (as strings) discovered on that webpage.
    Links are 'cleaned', meaning page anchor, email address, and telephone links
        are removed. Internal links are expanded to full URLs. Previously-visited
        URLs, URLs currently in the queue, and links to different domains are also removed.
    '''
    webpageURL = pageResponse.url
    parsedPage = BeautifulSoup(pageResponse.text, 'html.parser')

    # Find all valid links (not NoneType) from the <a> tags on the webpage
    links = []
    for link in parsedPage.find_all('a'):
        if (temp := link.get('href')):
            links.append(temp)

    # 'Clean' the links (see function docstring)
    linksClean = []
    for index, link in enumerate(links):
        # Ignore any links to the current page
        if link == '/':
            continue

        # Ignore page anchor links
        if '#' in link:
            continue

        # Ignore email address links
        if link[:7] == "mailto:":
            continue

        # Ignore telephone links
        if link[:4] == "tel:":
            continue

        # Expand internal links
        parsedURL = urlparse(webpageURL)
        if link[0] == '/':
            links[index] = parsedURL.scheme + "://" + parsedURL.hostname + link

        # Ignore links to other domains
        initalHost = (urlparse(INITIAL_URL)).hostname
        linkHost = (urlparse(links[index])).hostname
        if initalHost != linkHost:
            continue

        # Ignore all links to previously-visited URLs
        if links[index] in visitedLinks:
            continue

        # Ignore links that are already in the queue
        inQueue = False
        for url in urls:
            if url[0] == links[index]:
                inQueue = True
                break
        if inQueue:
            continue

        # Remove any dangling '/'s
        links[index] = links[index].rstrip('/')

        # All filters passed; link is appended to 'clean' list
        linksClean.append(links[index])

    # Remove any duplicate links in the list and return
    return list(set(linksClean))


def getScreenshot(driver, pageURL):
    """
    Accepts a web driver and a URL.
    Takes a screenshot of the full webpage and stores it in a local directory.
    Returns the file's path as a string.
    """
    # Assign and create a path for the screenshot
    # Directory format: './imgs/<URL-hostname>'
    directory = "./imgs/" + urlparse(pageURL).hostname
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Assign and create a filename for the screenshot
    # Filename format: <URL-path>.png
    if not (filename := urlparse(pageURL).path):
        filename = "index.png"
    else:
        filename = filename[1:].replace("/", "_") + ".png"

    # Resize the (headless) window to screenshot the page without scrolling
    # This helps avoid persistent nav/infobars, cookie notifications, and other alerts
    driver.get(pageURL)
    required_height = driver.execute_script('return document.body.parentNode.scrollHeight')
    driver.set_window_size(1280, required_height)
    # Note that we could change the width with the same method. But we keep window at
    # 'normal' width to prevent page elements from overlapping or covering others.

    # Take the screenshot and save it to the assigned path
    imagePath = directory + '/' + filename
    driver.save_screenshot(imagePath)

    # Return the window to original size
    driver.set_window_size(1280, 720)

    return imagePath


if __name__ == "__main__":
    # Check for valid number of arguments (2) in the script call.
    if (len(sys.argv) != 3):
        print("FATAL ERROR: Improper number of arguments. "
              "Please call program as: 'python app.py <URL> <MAX_DEPTH>")
        sys.exit()
    else:
        urls.append((INITIAL_URL, 0))   # Initial URL has a depth of 0
        startTime = time.time()         # Start timing how long program takes to run

    # Connect to a SQL database and create a table for the website
    tableName = ((urlparse(INITIAL_URL).hostname).replace('.', '')).replace('www', '')
    initializeDb(tableName)

    # Initialize and run a headless Chrome web driver
    chromeOptions = Options()
    chromeOptions.add_argument("--headless")
    chromeOptions.add_argument("--no-sandbox")
    chromeOptions.add_argument("--disable-notifications")
    chromeOptions.add_argument("--disable-infobars")
    chromeOptions.add_argument('--hide-scrollbars')
    chromeOptions.add_argument('--window-size=1280x720')
    driver = webdriver.Remote(command_executor='http://selenium-hub:4444/wd/hub', options=chromeOptions)

    # Initialization is now done; begin processing the queue
    websiteFaceCount = 0
    webpageVisitCount = 0
    for url in urls:
        pageURL = url[0]

        # Append current URL to 'visitedLinks' list to prevent visiting again later
        visitedLinks.append(pageURL)
        webpageVisitCount += 1

        # Use Requests package to obtain a 'Response' object from the webpage,
        # containing page's HTML, connection status, and other useful info.
        print(f"Attempting to connect to URL: {pageURL}")
        pageResponse = requests.get(pageURL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36'})

        # Perform error checking on the URL connection.
        # If webpage can't be properly connected to, an error is raised and
        # program skips to next url in the queue.
        pageStatus = pageResponse.status_code
        if pageStatus != 200:
            print(f"ERROR: {pageURL} could not be accessed (Response code: {pageStatus}")
            print("Continuing...")
            print("--------------------")
            continue
        else:
            print("Connected successfully. ", end='')

        # If the current webpage is not at MAX_DEPTH, get a list of links found
        # in the page's <a> tags. Links will be 'cleaned' (see function docstring)
        if url[1] < MAX_DEPTH:
            print("Finding links on page...")
            pageLinks = getLinks(pageResponse)
            for link in pageLinks:
                urls.append((link, url[1] + 1))
            print("Links appended to queue: ")
            print(f"{pageLinks}")

        # Save a screenshot of the webpage and get its path
        print("Attempting to screenshot page...")
        pageScreenshot = getScreenshot(driver, pageURL)
        print(f"Screenshot saved as {pageScreenshot}")
        print("Sending to Celery worker for processing...")

        # Send the screenshot to Celery for asynchronous processing (see tasks.py module)
        # Also appends the page's face count to the PostgresSQL database
        task = processImage.delay(pageURL, pageScreenshot)
        print("--------------------")

    # Webdriver no longer needed
    print("All URLs visited!")
    driver.quit()

    # Wait for Celery to finish processing queue of images
    print("Waiting on Celery to finish...")
    waitTimer = 0
    while not task.ready():
        time.sleep(1)
        waitTimer += 1
        if waitTimer == 10:
            print("Waiting on Celery to finish...")
            waitTimer = 0

    print("Celery finished processing!")
    print("--------------------")

    # Fetch data from database
    conn = psycopg2.connect(host='postgres', database='faceCrawler', user='postgres', password='postgres')
    cur = conn.cursor()
    cur.execute(sql.SQL("SELECT * FROM {};").format(sql.Identifier(tableName)))
    rows = cur.fetchall()

    # Count how many faces were detected on the entire website
    websiteFaceCount = 0
    for row in rows:
        websiteFaceCount += row[1]

    # Print results to the console
    print(f"Total number of faces found on {urlparse(INITIAL_URL).hostname}: {websiteFaceCount}")
    print(f"Total number of webpages analyzed: {webpageVisitCount}")
    print(f"Program took {(time.time() - startTime):.2f} seconds to run.")
