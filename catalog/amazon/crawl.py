#!/usr/local/bin/python2.5

import urllib2, re
from pprint import pprint
from time import sleep

# Amazon crawler

re_ul_ref = re.compile('<ul id="ref_\d+">')
re_books_cat = re.compile('<li style="margin-left: -?\d+px">.*Books')
re_cat_link1 = re.compile('<li style="margin-left: -?\d+px;"><a href=')
re_cat_link2 = re.compile('<a href="(.*?)".*?>.*?class="refinementLink">(.*?)</span>')

re_next_page = re.compile('<span class="pagnSep">\|</span><span class="pagnNext"><a href="(.*?)"  class="pagnNext" id="pagnNextLink"')
re_product_title = re.compile('<div class="productTitle"><a href=".*/dp/([^/]*)/.*">')

def read_page(f, read_cats=False):
    state = 4
    page = {'books': []}
    if read_cats:
        page['cats'] = []
        state = 0
    for line in f:
        if state == 0:
            if line.startswith("<h2>Category</h2>"):
                state = 1
            continue
        if state == 1:
            assert re_ul_ref.match(line)
            state = 2
            continue
        if state == 2:
            assert re.compile('<li style="margin-left: -?\d+px">.*Books')
            state = 3
            continue
        if state == 3:
            if line.startswith('</ul>'):
                state = 4
                continue
            if not re_cat_link1.match(line):
                continue
            m = re_cat_link2.search(line)
            assert m
            page['cats'].append({'url': m.group(1), 'title': m.group(2)})
            continue
            (url, title) = m.groups()
            title = title.replace('&amp;', '&')
            books['cats'].append({'url': url, 'title': title})
        if state == 4:
            if line.startswith('<div class="header"><div class="resultCount">'):
                state = 5
            continue
        if state == 5:
            if line.startswith('<div class="sortBy">'):
                state = 6
            elif line.startswith('<span class="pagnSep">|</span><span class="pagnNext">'):
                m = re_next_page.match(line)
                assert m
                page['link'] = m.group(1)
                state = 6
            continue
        if state == 6:
            if line.find('<div class=listView>') != -1:
                state = 7
            continue
        if state == 7:
            if line.startswith('<div id="bottomBox">'):
                break
            if line.startswith('<div id="sponsoredLinks">'):
                break
            if line.find('<div class="productTitle">') != -1:
                m = re_product_title.search(line)
                assert m
                page['books'].append(m.group(1))
            continue
    return page

def urlopen(url):
    request = urllib2.Request(url)
    request.add_header('User-Agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071618 Firefox/3.0b3pre (Debian-3.0.1-1)')
    return urllib2.urlopen(request)

out = open('out', 'w')

def get_page(url, depth = 0):
    f = urlopen(url)
    page = read_page(f, read_cats=True)
    f.close()
    for isbn in page['books']:
        print >> out, isbn
    cats = page['cats']

    while 'link' in page:
        f = urlopen("http://amazon.com" + page['link'])
        page = read_page(f, read_cats=False)
        f.close()
        for isbn in page['books']:
            print >> out, isbn

    for cat in cats:
        print " " * depth, cat['title']
        get_page("http://amazon.com" + cat['url'], depth + 1)

root_url = 'http://www.amazon.com/s/qid=1220873277/ref=sr_ex_n_1?ie=UTF8&rs=1&sort=editionspsrank&bbn=1&rh=i%3Astripbooks%2Cp_n_feature_browse-bin%3A618083011'
get_page(root_url)
out.close()
