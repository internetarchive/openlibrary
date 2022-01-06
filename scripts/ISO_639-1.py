import json 
import requests 
from bs4 import BeautifulSoup # library to parse HTML documents
import pandas as pd # library for data analysis

#GET INFORMATION FROM List_of_ISO_639-1_codes
wikiurl="https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes"
table_class="wikitable sortable jquery-tablesorter"
response=requests.get(wikiurl)

# parse data from the html into a beautifulsoup object
soup = BeautifulSoup(response.text, 'html.parser')
indiatable=soup.find('table',{'class':"wikitable"})

df=pd.read_html(str(indiatable))
df=pd.DataFrame(df[0])

columns = df[["639-1", "639-2/B"]]

ISO = {row['639-2/B']:row['639-1'] for index, row in df.iterrows()}

#GET DATA FROM Languages.page
with open ("openlibrary/plugins/openlibrary/pages/languages.page", "r") as languages :
  data=json.load(languages)
  for line in data:
    code=line["code"]
    if code in ISO:
     ISO_1=ISO[code]
     line["iso_639_1"] = ISO_1
  
  render_languagues=json.dumps(data, indent = 2)

with open("openlibrary/plugins/openlibrary/pages/new_languages.page","w") as file:
  file.write(render_languagues)
  
    



