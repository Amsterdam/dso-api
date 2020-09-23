import time
from pprint import pprint
from zapv2 import ZAPv2


def test_owasp_check():
    """ Prove that there are no HIGH risk vulnerabilities detected """
    # The URL of the application to be tested
    target = "https://acc.api.data.amsterdam.nl/v1/"
    apiKey = None

    # setup ZAP connection and point to ZAP proxy (a docker container)
    # You can also access the ZAP GUI (and envoke scans or get data)
    # by browsing to localhost:8090
    zap = ZAPv2(
        apikey=apiKey,
        proxies={"http": "http://127.0.0.1:8090", "https": "http://127.0.0.1:8090"},
    )

    # start spider to get URL's
    print("Spidering target {}".format(target))
    # The scan returns a scan id to support concurrent scanning
    #zap.spider.set_option_max_children = 0
    #zap.spider.set_option_max_depth = 0
    scanID = zap.spider.scan(target)
    while int(zap.spider.status(scanID)) < 100:
        # Poll the status until it completes
        print(f"Spider progress: {zap.spider.status(scanID)}, scan id: {scanID}")
        time.sleep(1)

    print("Spider has completed!")

    # with active scanning, attacks are simulated on the target
    print("Active Scanning target {}".format(target))
    zap.core.set_mode('ATTACK')
    scanID = zap.ascan.scan(target)
    while int(zap.ascan.status(scanID)) < 100:
        # Loop until the scanner has finished
        print(f"Scan progress: {zap.ascan.status(scanID)}, scan id: {scanID}")
        time.sleep(5)
    print("Active Scan completed")

    # print vulnerabilities found by the scanning
    print("Hosts: {}".format(", ".join(zap.core.hosts)))
    print("Alerts: ")
    results = {}
    for result in zap.core.alerts(baseurl=target):
        results[result["risk"] + ":" + result["name"]] = (
            result["evidence"] + "-- description: " + result["description"]
        )

    pprint(results)
    alerts = zap.alert.alerts(baseurl=target)
    alert_count = len(alerts)
    print("Total number of alerts: " + str(alert_count))

    # setup risk bucket to check if there is a High risk vulnerability detected
    risk_bucket = {}
    risk_bucket["Low"] = None
    risk_bucket["Medium"] = None
    risk_bucket["High"] = None
    for key in results.keys():
        if "Low" in key:
            risk_bucket["Low"] = True
        if "Medium" in key:
            risk_bucket["Medium"] = True
        if "High" in key:
            risk_bucket["High"] = True

    assert risk_bucket["High"] is None
