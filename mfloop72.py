#!/usr/bin/env python

# by teknohog

# Automatic assignment handler for manual testing at gpu72.com and
# mersenne.org.

# Written with mfakto in mind, might work with other
# similar applications.

# This version runs in parallel with mfakto. It uses lockfiles to
# avoid conflicts when updating files.

import sys
import os.path
import cookielib
import urllib2
import re
from time import sleep
import os
import urllib

primenet_baseurl = "http://www.mersenne.org/"
gpu72_baseurl = "http://www.gpu72.com/"

def ass_generate(assignment):
    output = ""
    for key in assignment:
        output += key + "=" + assignment[key] + "&"
    #return output.rstrip("&")
    return output

def cleanup(data):
    # as in submit_spider; urllib2.quote does not quite work here
    output = re.sub(" ", "+", data)
    output = re.sub(":", "%3A", output)
    output = re.sub(",", "%2C", output)
    output = re.sub("\n", "%0A", output)
    return output

def debug_print(text):
    if options.debug:
        print(progname + ": " + text)

def greplike(pattern, l):
    output = []
    for line in l:
        s = re.search(r".*(" + pattern +")$", line)
        if s:
            output.append(s.groups()[0])
    return output

def num_topup(l, targetsize):
    num_existing = len(l)
    num_needed = targetsize - num_existing
    return max(num_needed, 0)

def readonly_file(filename):
    # Used when there is no intention to write the file back, so don't
    # check or write lockfiles. Also returns a single string, no list.
    if os.path.exists(filename):
        File = open(filename, "r")
        contents = File.read()
        File.close()
    else:
        contents = ""

    return contents

def read_list_file(filename):
    # Used when we plan to write the new version, so use locking
    lockfile = filename + ".lck"

    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL)
        os.close(fd)

        if os.path.exists(filename):
            File = open(filename, "r")
            contents = File.readlines()
            File.close()
            return map(lambda x: x.rstrip(), contents)
        else:
            return []

    except OSError, e:
        if e.errno == 17:
            return "locked"
        else:
            raise

def write_list_file(filename, l):
    # Assume we put the lock in upon reading the file, so we can
    # safely write the file and remove the lock
    lockfile = filename + ".lck"

    content = "\n".join(l) + "\n"
    File = open(filename, "w")
    File.write(content)
    File.close()

    os.remove(lockfile)

def get_assignment():
    w = read_list_file(workfile)
    if w == "locked":
        return "locked"

    tasks = greplike(workpattern, w)

    num_to_get = num_topup(tasks, int(options.num_cache))

    if num_to_get < 1:
        debug_print("Cache full, not getting new work")
    else:
        assignment = {"Number": str(num_to_get),
                      "GHzDays": "",
                      "Low": "0",
                      "High": "10000000000",
                      "Pledge": options.max_exp,
                      "Option": "0",
                  }
        
        debug_print("Fetching " + str(num_to_get) + " assignments")

        # This makes a POST instead of GET
        data = urllib.urlencode(assignment)
        req = urllib2.Request(gpu72_baseurl + "/account/getassignments/lltf/", data)
        try:
            r = gpu72.open(req)
            rlines = r.readlines()
            noavail = greplike("No assignments available.*", rlines)

            if len(noavail) > 0:
                debug_print(noavail[0])
            else:
                new_tasks = greplike(workpattern, rlines)
                # Remove dupes
                tasks += list(set(new_tasks))

        except urllib2.URLError:
            debug_print("URL open error")

    write_list_file(workfile, tasks)

def mersenne_find(line, complete=True):
    work = readonly_file(workfile)

    s = re.search(r"M([0-9]*) ", line)
    if s:
        mersenne = s.groups()[0]
        if not "," + mersenne + "," in work:
            return complete
        else:
            return not complete
    else:
        return False

def submit_work():
    # Only submit completed work, i.e. the exponent must not exist in
    # worktodo.txt any more

    files = [resultsfile, sentfile]
    rs = map(read_list_file, files)

    if "locked" in rs:
        # Remove the lock in case one of these was unlocked at start
        for i in range(len(files)):
            if rs[i] != "locked":
                write_list_file(files[i], rs[i])
                
        return "locked"

    (results, sent) = rs

    # Use the textarea form to submit several results at once.

    # Useless lines (not including a M#) are now discarded completely.

    results_send = filter(mersenne_find, results)
    results_keep = filter(lambda x: mersenne_find(x, complete=False), results)

    if len(results_send) == 0:
        debug_print("No complete results found to send.")
        # Don't just return here, files are still locked...
    else:
        while len(results_send) > 0:
            sendbatch = []
            while sum(map(len, sendbatch)) < sendlimit and \
                  len(results_send) > 0:
                sendbatch.append(results_send.pop(0))

            data = "\n".join(sendbatch)
        
            debug_print("Submitting\n" + data)

            try:
                r = primenet.open(primenet_baseurl + "manual_result/default.php?data=" + cleanup(data) + "&B1=Submit")
                if "Processing result" in r.read():
                    sent += sendbatch
                else:
                    results_keep += sendbatch
                    debug_print("Submission failed.")
            except urllib2.URLError:
                results_keep += sendbatch
                debug_print("URL open error")

    write_list_file(resultsfile, results_keep)
    write_list_file(sentfile, sent)

from optparse import OptionParser
parser = OptionParser()

parser.add_option("-d", "--debug", action="store_true", dest="debug", default=False, help="Display debugging info")

parser.add_option("-e", "--exp", dest="max_exp", default="72", help="Upper limit of exponent, default 72")

parser.add_option("-u", "--username", dest="username", help="Primenet user name")
parser.add_option("-p", "--password", dest="password", help="Primenet password")
parser.add_option("-w", "--workdir", dest="workdir", default=".", help="Working directory with worktodo.txt and results.txt, default current")

parser.add_option("-U", "--gpu72user", dest="guser", help="GPU72 user name")
parser.add_option("-P", "--gpu72pass", dest="gpass", help="GPU72 password")

parser.add_option("-n", "--num_cache", dest="num_cache", default="1", help="Number of assignments to cache, default 1")

parser.add_option("-t", "--timeout", dest="timeout", default="3600", help="Seconds to wait between network updates, default 3600. Use 0 for a single update without looping.")

(options, args) = parser.parse_args()

progname = os.path.basename(sys.argv[0])
workdir = os.path.expanduser(options.workdir)
timeout = int(options.timeout)

workfile = os.path.join(workdir, "worktodo.txt")

resultsfile = os.path.join(workdir, "results.txt")

# A cumulative backup
sentfile = os.path.join(workdir, "results_sent.txt")

# Trial factoring
workpattern = r"Factor=.*(,[0-9]+){3}"

# mersenne.org limit is about 4 KB; stay on the safe side
sendlimit = 3500

# adapted from http://stackoverflow.com/questions/923296/keeping-a-session-in-python-while-making-http-requests
primenet_cj = cookielib.CookieJar()
primenet = urllib2.build_opener(urllib2.HTTPCookieProcessor(primenet_cj))

# Basic http auth
password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
password_mgr.add_password(None, gpu72_baseurl + "/account/", options.guser, options.gpass)
handler = urllib2.HTTPBasicAuthHandler(password_mgr)
gpu72 = urllib2.build_opener(handler)

while True:
    # GPU72 needs no separate login
    while get_assignment() == "locked":
        debug_print("Waiting for worktodo.txt access...")
        sleep(2)

    # Log in to primenet for work submission
    try:
        r = primenet.open(primenet_baseurl + "account/?user_login=" + options.username + "&user_password=" + options.password + "&B1=GO")

        if not options.username + " logged-in" in r.read():
            debug_print("Login failed.")
        else:
            while submit_work() == "locked":
                debug_print("Waiting for results file access...")
                sleep(2)

    except urllib2.URLError:
        debug_print("Primenet URL open error")

    if timeout <= 0:
        break
            
    sleep(timeout)
