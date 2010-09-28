# coding=utf-8
from catalog.get_ia import read_marc_file
from catalog.read_rc import read_rc
from time import time
from catalog.marc.fast_parse import index_fields, get_tag_lines, get_first_tag, get_all_subfields
import web, os, os.path, re, sys

titles = [ "Accolade", "Adi", "Aetheling", "Aga Khan", "Ajaw", "Ali'i", 
        "Allamah", "Altgrave", "Ammaveedu", "Anji", "Ryūkyū", "Archtreasurer", 
        "Aryamehr", "Atabeg", "Ban", "Baron", "Batonishvili", "Begum", "Bey", 
        "Boier", "Boyar", "Bulou", "Burgmann", "Buring Khan", "Caliph", 
        "Castellan", "Chakravatin", "Comte", "Conde", "Count",
        "Count palatine", "Countess", "Crown prince", "Daula", 
        "Despot", "Doge", "Dowager", "Duchess of Rothesay", "Duke", "Earl", 
        "Edler", "Elector", "Elteber", "Emir", "Emperor", "Emperor-elect", 
        "Erbherr", "Feudal baron", "Fils de France", "Fraujaz", "Fürst",
        "Grand duke", "Grand prince", "Grand Župan", "Grandee", "Haty-a", 
        "Hersir", "Hidalgo", "Highness", "Hold", "Hteik Tin", "Ichirgu-boil", 
        "Infante", "Jang", "Jarl", "Jonkheer", "Junker", "Kavkhan", "Khagan", 
        "Khagan Bek", "Khan", "Khanum", "Khatun", "Knight", "Knyaz",
        "Kodaw-gyi", "Kralj", "Lady", "Lamido", "Landgrave", "Lendmann", 
        "Lord", "Madame Royale", "Magnate", "Maha Uparaja", 
        "Maha Uparaja Anaudrapa Ainshe Min", "Maharaja", "Maharajadhiraja", 
        "Maharana", "Maharao", "Maharaol", "Malik", "Margrave", "Marquess", 
        "Marquis de Bauffremont", "Marquise", "Mepe-Mepeta", "Mesne lord", 
        "Mian", "Min Ye", "Min-nyi Min-tha", "Mir", "Mirza", "Monsieur", "Mormaer", "Morza", "Mwami", "Naib", "Nawab", "Nayak", "Negus", "Nobile", "Obalumo", "Orangun", "Aftab", "Ottoman", "Padishah", "Paigah", "Hyderabad", "Paladin", "Palaiyakkarar", "Palatine", "Panapillai Amma", "Paramount Ruler", "Pasha", "Patricianship", "Pharaoh", "Piast dynasty", "Prescriptive barony", "Prince", "Prince du Sang", "Prince-Bishop", "Princely Highness", "Princeps", "Princess", "Principalía", "Privy chamber", "Rai", "Raja", "Rajah Muda of Sarawak", "Rajus", "Rana", "Rao Raja", "Ratu", "Ridder", "Ro", "Roko", "Sado Min", "Sahib", "Samanta", "Sawai Maharaja", "Shah", "Shahzada", "Shamkhal", "Shanyu", "Shwe Kodaw-gyi", "Shwe Kodaw-gyi Awratha", "Shwe Kodaw-gyi Rajaputra", "Sidi", "Sir", "Sultan", "Sunan", "Susuhunan", "Szlachta", "Tenant-in-chief", "Thakur", "Thampi", "Tsar", "Tsarevitch", "Tu'i", "Ueekata", "Uparaja", "Uparat", "Viceroy", "Victory", "Vidame", "Viscount", "Vizier", "Wazirzada", "Yang di-Pertuan Besar", "Zamindar", "Zeman", "Župa"]

rc = read_rc()
web.config.db_parameters = dict(dbn='postgres', db='ol_merge', user=rc['user'], pw=rc['pw'], host=rc['host'])
web.config.db_printing = False
web.load()

def sources():
    return ((i.id, i.archive_id, i.name) for i in web.select('marc_source'))

def process_record(pos, loc, data):
    for tag in '100', '700':
        line = get_first_tag(data, set([tag]))
        if line:
            fields = list(get_all_subfields(line))
            if any(k == 'c' for k, v in fields):
                print (loc, fields)

def files(ia):
    endings = ['.mrc', '.marc', '.out', '.dat', '.records.utf8']
    def good(filename):
        return any(filename.endswith(e) for e in endings)

    dir = rc['marc_path'] + ia
    dir_len = len(dir) + 1
    files = []
    for dirpath, dirnames, filenames in os.walk(dir):
        files.extend(dirpath + "/" + f for f in sorted(filenames))
    return [(i[dir_len:], os.path.getsize(i)) for i in files if good(i)]

rec_no = 0

for source_id, ia, name in sources():
    for part, size in files(ia):
        full_part = ia + "/" + part
        filename = rc['marc_path'] + full_part
        assert os.path.exists(filename)
        f = open(filename)
        for pos, loc, data in read_marc_file(full_part, f):
            rec_no +=1
            process_record(pos, loc, data)
