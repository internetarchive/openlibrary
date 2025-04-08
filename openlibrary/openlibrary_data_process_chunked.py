"""  
Convert your txt files into smaller csv files which are easier to load into the db.
Decide how large you would like to make each chunk.
For editions, 3 million lines was about 3.24 gigs and about an hour to load.
"""

import csv
import ctypes as ct
import os

# Optional if you want to make a smaller copy from the unzipped version for testing
# sed -i '' '100000,$ d' ./data/unprocessed/ol_dump_editions.txt

# You can run this file once with all 3 downloaded and unzipped files or run it as they come in.
# Just make sure the end product in filenames.txt  looks like this
# authors	0	False	{authors_2000.csv,authors_4000.csv,authors_6000.csv}
# works	1	False	{works_2000.csv,works_4000.csv,works_6000.csv,works_8000.csv}
# editions	2	False	{editions_2000.csv,editions_4000.csv,editions_6000.csv}

# See https://stackoverflow.com/a/54517228 for more info on this
csv.field_size_limit(int(ct.c_ulong(-1).value // 2))

LINES_PER_FILE = 2000000

INPUT_PATH = "./data/unprocessed/"
OUTPUT_PATH = "./data/processed/"

FILE_IDENTIFIERS = ['authors', 'works', 'editions']


def run():
    """Run the script."""

    filenames_array = []
    file_id = 0

    for identifier in FILE_IDENTIFIERS:
        print('Currently processing ', identifier)

        filenames = []
        csvoutputfile = None

        with open(os.path.join(INPUT_PATH, ('ol_dump_' + identifier + '.txt')), encoding="utf-8")as cvsinputfile:
            reader = csv.reader(cvsinputfile, delimiter='\t')

            for line, row in enumerate(reader):

                if line % LINES_PER_FILE == 0:
                    if csvoutputfile:
                        csvoutputfile.close()

                    filename = identifier + \
                        '_{}.csv'.format(line + LINES_PER_FILE)

                    filenames.append(filename)
                    csvoutput = open(os.path.join(
                        OUTPUT_PATH, filename), "w", newline="", encoding="utf-8")
                    writer = csv.writer(
                        csvoutput, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)

                if len(row) > 4:
                    writer.writerow(
                        [row[0], row[1], row[2], row[3], row[4]])

            if csvoutputfile:
                csvoutputfile.close()

        filenames_array.append([identifier,  str(file_id), False, filenames])

        print('\n', identifier, 'text file has now been processed.\n')
        print(identifier,  str(file_id), filenames)
        file_id += 1

    # list of filenames that can be loaded into database for automatic file reading.
    filenamesoutput = open(os.path.join(
        OUTPUT_PATH, "filenames.txt"), "a", newline="", encoding="utf-8")
    filenameswriter = csv.writer(
        filenamesoutput, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
    for row in filenames_array:

        filenameswriter.writerow(
            [row[0], row[1], row[2], '{' + ','.join(row[3]).strip("'") + '}'])

    filenamesoutput.close()

    print("Process complete")


run()
