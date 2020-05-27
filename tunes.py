#!/usr/bin/env python3

########################################################################################################################

# Tunes
# =====

# A script for searching and displaying tunes from (at the moment) thesession.org as PDF files

# Requirements
# ------------

# 1. Python 3.7 + lxml and requests (pip install lxml requests)
# 2. For rendering ABC notation: https://github.com/leesavide/abcm2ps/
# 3. As a user interface: https://github.com/davatorium/rofi (dmenu could probably also be used)
# 4. A PDF reader that can read from stdin, I use zathura


# Usage
# -----

# Add execute permissions:
#   chmod +x tunes.py
# And execute:
#   ./tunes.py
# You can also search for a tune directly, say "Farewell to Ireland" and run:
#   ./tunes.py Farewell to Ireland


########################################################################################################################

import subprocess
import sys
from collections import namedtuple

from lxml import html

import requests

Tune = namedtuple('Tune', ('name', 'id', 'type'))
TuneSetting = namedtuple('TuneSetting', ('id', 'meter', 'key', 'abc'))

# Commands, you may use your own programs here:
# ---

# PDF viewer, the command needs to be able to a PDF from stdin (like `zathura -` does)
PDF_VIEWER_CMD = ['zathura', '-']
# A converter from ps to pdf, again it must be able to read from stdin and write to stdout
PS2PDF_CMD = ['ps2pdf', '-', '-']
# A converter from abc notation to ps, again it must be able to read from stdin and write to stdout
ABC2PS_CMD = ['abcm2ps', '-', '-O', '-']


# Parsing constants, highly dependant on thesession.org
# ---

# Endpoints
TUNES_EP = 'https://thesession.org/tunes/{tune_id}'
SEARCH_EP = 'https://thesession.org/tunes/search?type=&mode=&q={query}'
POPULAR_TUNES_EP = 'https://thesession.org/tunes/popular'

# XPaths
POPULAR_BASE_XPATH = "descendant::span[@class='manifest-item-title']"
POPULAR_NAME_XPATH = '/'.join([POPULAR_BASE_XPATH, "a[@data-tuneid]/text()"])
POPULAR_ID_XPATH = '/'.join([POPULAR_BASE_XPATH, "a/@data-tuneid"])
POPULAR_TYPE_XPATH = '/'.join([POPULAR_BASE_XPATH, "a[@class='detail']/text()"])

SEARCH_BASE_XPATH = "descendant::li[@class='manifest-item']"
SEARCH_NAME_XPATH = '/'.join([SEARCH_BASE_XPATH, "a[@data-tuneid]/text()"])
SEARCH_ID_XPATH = '/'.join([SEARCH_BASE_XPATH, "a/@data-tuneid"])
SEARCH_TYPE_XPATH = '/'.join([SEARCH_BASE_XPATH, "span[@class='manifest-item-title detail']/text()"])

BASE_SETTING_XPATH = "descendant::div[@class='setting-abc']/div[@class='notes']"


def get_popular_tunes():
    resp = requests.get(POPULAR_TUNES_EP)
    resp.raise_for_status()

    tree = html.fromstring(resp.content)
    tunes = [Tune(*elem) for elem in zip(tree.xpath(POPULAR_NAME_XPATH),
                                         tree.xpath(POPULAR_ID_XPATH),
                                         tree.xpath(POPULAR_TYPE_XPATH))]
    return tunes


def get_search_tunes(query=""):
    resp = requests.get(SEARCH_EP.format(query=query))
    resp.raise_for_status()

    tree = html.fromstring(resp.content)
    tunes = [Tune(*elem) for elem in zip(tree.xpath(SEARCH_NAME_XPATH),
                                         tree.xpath(SEARCH_ID_XPATH),
                                         map(lambda s: s.strip('\n'), tree.xpath(SEARCH_TYPE_XPATH)))]
    return tunes


def get_tune_settings(tune_id):
    resp = requests.get(TUNES_EP.format(tune_id=tune_id))
    resp.raise_for_status()

    tree = html.fromstring(resp.content)
    elements = tree.xpath(BASE_SETTING_XPATH)

    settings = []

    for element in elements:
        s_id, s_meter, s_key, s_abc = None, None, None, []
        for line in element.text_content().split('\n'):
            if line:
                ls = line.split(':')
                if ls[0] == 'X':
                    s_id = ls[1].strip()
                elif ls[0] == 'M':
                    s_meter = ls[1].strip()
                elif ls[0] == 'K':
                    s_key = ls[1].strip()
                s_abc.append(line)
        settings.append(TuneSetting(id=s_id, meter=s_meter, key=s_key, abc='\n'.join(s_abc)))

    return settings


class SearchException(Exception):
    def __init__(self, query):
        self._query = query

    @property
    def query(self):
        return self._query


# rofi / dmenu funcions
ROFI_TUNE_PROMPT = "tune: "
TUNE_PREFIX = '♫'

ROFI_SETTING_PROMPT = "setting: "
SETTING_PREFIX = '♬'


def _format_tunes(tunes):
    return '\n'.join("{prefix} {tune_name} [{tune_type}]".format(prefix=TUNE_PREFIX,
                                                                 tune_name=tune.name,
                                                                 tune_type=tune.type)
                     for tune in tunes)


def _format_settings(settings):
    return '\n'.join("{prefix} ({id}) {key} {meter}".format(prefix=SETTING_PREFIX,
                                                            id=setting.id,
                                                            key=setting.key,
                                                            meter=setting.meter)
                     for setting in settings)


def select_tune(tunes):
    rofi_command = ['rofi', '-dmenu', '-i', '-format', 'i:s', '-p', ROFI_TUNE_PROMPT]
    input_str = _format_tunes(tunes)

    rofi_result = subprocess.run(rofi_command, input=input_str, stdout=subprocess.PIPE, encoding='utf-8')

    if rofi_result.returncode != 0:
        exit(rofi_result.returncode)

    rofi_output = rofi_result.stdout.split(":")
    index = int(rofi_output[0])
    if index < 0:
        raise SearchException(rofi_output[1])
    tune = tunes[index]

    return tune


def select_setting(settings):
    rofi_command = ['rofi', '-dmenu', '-i', '-format', 'i:s', '-p', ROFI_SETTING_PROMPT]
    input_str = _format_settings(settings)

    rofi_result = subprocess.run(rofi_command, input=input_str, stdout=subprocess.PIPE, encoding='utf-8')

    if rofi_result.returncode != 0:
        exit(rofi_result.returncode)

    rofi_output = rofi_result.stdout.split(":")
    index = int(rofi_output[0])
    if index < 0:
        raise ValueError("Must select a valid setting!")
    setting = settings[index]

    return setting


# display


def display_abc(abc):
    pdf_viewer = subprocess.Popen(PDF_VIEWER_CMD, stdin=subprocess.PIPE)
    ps2pdf = subprocess.Popen(PS2PDF_CMD, stdin=subprocess.PIPE, stdout=pdf_viewer.stdin)
    abcm2ps = subprocess.Popen(ABC2PS_CMD, stdin=subprocess.PIPE, stdout=ps2pdf.stdin)
    abcm2ps.communicate(input=abc.encode('utf-8'))
    ps2pdf.communicate()
    pdf_viewer.stdin.close()


# search utility

def search_and_display(query=""):
    tune = None
    while not tune:
        try:
            tune = select_tune(get_search_tunes(query=query))
        except SearchException as se:
            query = se.query

    display_abc(
        select_setting(
            get_tune_settings(tune.id)
        ).abc
    )


if __name__ == '__main__':
    query = " ".join(sys.argv[1:])
    search_and_display(query=query)
