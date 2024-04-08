'''
Run from root of openlibrary like so:
PYTHONPATH=$(PWD) python3 scripts/open_syllabus_project_parser.py

A python script that takes as an argument one directory.

In that that directory there are files named as follows:
part-00000-d2b72298-1996-464d-b238-27e4737d69ab-c000.json.gz
part-00001-d2b72298-1996-464d-b238-27e4737d69ab-c000.json.gz
part-00002-d2b72298-1996-464d-b238-27e4737d69ab-c000.json.gz
etc

The contents of the uncompressed json files has json like this,
one per line:
{
    "ol_id": "/works/OL194763W",
    "Accounting": 0,
    "Agriculture": 0,
    "Anthropology": 0,
    "Architecture": 0,
    "Astronomy": 0,
    "Atmospheric Sciences": 0,
    "Basic Computer Skills": 0,
    "Basic Skills": 0,
    "Biology": 0,
    "Business": 0,
    "Career Skills": 0,
    "Chemistry": 0,
    "Chinese": 0,
    "Classics": 0,
    "Computer Science": 0,
    "Construction": 0,
    "Cosmetology": 0,
    "Criminal Justice": 0,
    "Criminology": 0,
    "Culinary Arts": 0,
    "Dance": 0,
    "Dentistry": 0,
    "Earth Sciences": 0,
    "Economics": 0,
    "Education": 0,
    "Engineering": 0,
    "Engineering Technician": 0,
    "English Literature": 0,
    "Film and Photography": 0,
    "Fine Arts": 0,
    "Fitness and Leisure": 0,
    "French": 0,
    "Geography": 0,
    "German": 0,
    "Health Technician": 0,
    "Hebrew": 0,
    "History": 0,
    "Japanese": 0,
    "Journalism": 0,
    "Law": 0,
    "Liberal Arts": 0,
    "Library Science": 0,
    "Linguistics": 0,
    "Marketing": 0,
    "Mathematics": 0,
    "Mechanic / Repair Tech": 0,
    "Media / Communications": 0,
    "Medicine": 0,
    "Military Science": 0,
    "Music": 0,
    "Natural Resource Management": 0,
    "Nursing": 0,
    "Nutrition": 0,
    "Philosophy": 0,
    "Physics": 0,
    "Political Science": 0,
    "Psychology": 0,
    "Public Administration": 0,
    "Public Safety": 0,
    "Religion": 0,
    "Sign Language": 0,
    "Social Work": 0,
    "Sociology": 0,
    "Spanish": 0,
    "Theatre Arts": 0,
    "Theology": 1,
    "Transportation": 0,
    "Veterinary Medicine": 0,
    "Women's Studies": 0,
    "total": 1
}
'''

from openlibrary.utils.open_syllabus_project import generate_osp_db
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

FnToCLI(generate_osp_db).run()
