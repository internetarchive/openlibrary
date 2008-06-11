import sys
import types
import string
import re
from MARC21Exn import MARC21Exn

import pdb
# pdb.set_trace()

from MARC21Charset import marc8_to_unicode_converter
marc8_to_unicode = marc8_to_unicode_converter ()

# tweaked by dbg and phr at the Internet Archive from the version described below.

#-- Version 1.0.1
#-- November 1, 2000
#-- Due to a recent discovery (thanks to Sue Trombley) that MARC21 records
#-- can have multiple instances of both fields and subfields, I've changed
#-- the MARC21Record and MARC21DataField classes to handle this.
#-- Now, the fields of a MARC21Record can either be a single instance or 
#-- a list of instances of the MARC21DataField class.  Similarly for the
#-- subfields.  The contents of M['450']['a'] may be a single string or
#-- a list of strings.

# However, a MARC21Record or a MARC21DataField which has been created by
# parsing data (and which has not subsequently been modified via
# __setitem__) will always have fields that are lists.


class NoDefault:
        pass

class MARC21Record:
        FIELD_TERMINATOR=chr(30)
        RECORD_TERMINATOR=chr(29)
        character_coding_schemes = {
                ' ': "MARC-8",
                'a': "UCS/Unicode"
        }

        def __init__(self,data=None,file_pos=None):
                self.raw_data=data
                self.file_pos=file_pos

                self.control_number=''
                self.dataFields={}
                self.record_status=' '
                self.type_of_record=' '
                self.implementation_defined1='  '
                self.character_coding_scheme=' '
                self.implementation_defined2='   '

                #-- "constants" according to the MARC21 standard.
                self.entry_map='4500'
                self.indicator_count=2
                self.subfield_code_length=2
                
                if data is not None:
                        self.parse(data)

        def warn (self, msg):
                sys.stderr.write ("record at file-offset %d: %s\n" % (self.file_pos, msg))

        def err (self, msg):
                raise MARC21Exn ("record at file-offset %d: %s" % (self.file_pos, msg))

        def parse(self,data):
                #-- Extract the leader from the data.
                leaderData=data[:24]
                data=data[24:]

                self.leader = leaderData

                #-- Read the fields in the leader and modify the state of the object.
                lengthOfRecord=int(leaderData[:5])
                if len(self.raw_data) < lengthOfRecord:
                        raise MARC21Exn ("truncated record (length %d should be %d)"%(len(self.raw_data), lengthOfRecord))
                self.record_status=leaderData[5]
                self.type_of_record=leaderData[6]
                self.implementation_defined1=leaderData[7:9]
                self.character_coding_scheme=leaderData[9]
                self.indicator_count=int(leaderData[10])
                self.subfield_code_length=int(leaderData[11])
                baseAddressOfData=int(leaderData[12:17])
                self.implementation_defined2=leaderData[17:20]
                self.entry_map=leaderData[20:24]

                if self.indicator_count != 2:
                        self.err ("indicator count (%d) is not 2" % self.indicator_count);
                if self.subfield_code_length != 2:
                        self.err ("subfield code length (%d) is not 2" % self.subfield_code_length);

                #-- Now, read the remaining data until a FIELD_TERMINATOR.
                #-- This data will be the directory.
                FTindex=string.find(data,MARC21Record.FIELD_TERMINATOR)
                directoryData=data[:FTindex]
                data=data[FTindex+1:]
                fields_data_len=len(data)

                #-- Parse the directory.
                directory={}
                last_tag=''
                while len(directoryData)>0:
                        directoryEntry=directoryData[:12]
                        tag=directoryData[:3]
                        if tag < last_tag:
                                raise MARC21Exn ("bad order of directory entries: jumped from \"~s\" to \"~s\"" % (last_tag, tag))
                        fieldLength=int(directoryData[3:7])
                        fieldOffset=int(directoryData[7:12])
                        if fieldLength == 0:
                                self.err ("found zero-length directory entry with tag \"~s\"" % tag)
                        elif fieldOffset + fieldLength > fields_data_len:
                                self.err ("found out-of-range directory entry with tag \"%s\" and extent %d:%d+%d"
                                        % (tag, fields_data_len, fieldOffset, fieldLength))
                        else:
                                if directory.has_key(tag):
                                        directory[tag].append((fieldLength,fieldOffset))
                                else:
                                        directory[tag]=[(fieldLength,fieldOffset)]
                        directoryData=directoryData[12:]

                #-- Now, use the directory to read in the following data.
                for tag in directory.keys():
                        for directoryEntry in directory[tag]:
                                fieldLength,fieldOffset=directoryEntry
                                fieldData=data[fieldOffset:fieldOffset+fieldLength]
                                taggedData = None;
                                if isControlFieldTag(tag):
                                        if fieldData[-1] != MARC21Record.FIELD_TERMINATOR:
                                                raise MARC21Exn ("bad control-field terminator")
                                        control_field_data = fieldData[:-1]
                                        taggedData=MARC21ControlField(control_field_data)
                                        if tag == '001':
                                                self.control_number = control_field_data
                                else:
                                        taggedData=MARC21DataField(self,tag,fieldData)
                                if taggedData is not None:
                                        if self.dataFields.has_key(tag):
                                                self.dataFields[tag].append(taggedData)
                                        else:
                                                self.dataFields[tag]=[taggedData]

        def fields(self):
                return self.dataFields.keys()
                
        def __getitem__(self,tag):
                return self.dataFields[tag]

        def get_field (self, tag, default=NoDefault):
                vals = self.dataFields.get (tag, [])
                nvals = len(vals)
                if nvals == 0:
                        if default is not NoDefault:
                                return default
                        else:
                                raise MARC21Exn ("no value for field %s" % tag)
                elif nvals == 1:
                        return vals[0]
                else:
                        raise MARC21Exn ("more than one value for field %s" % tag)

        def get_fields (self, tag):
                return self.dataFields.get (tag, [])

        def __setitem__(self,tag,value):
                if tag[:2]=='00':
                        if type(value)!=types.StringType:
                                #-- 00x tags are control fields.  They have no subfields,
                                #-- so their data type is just a string.
                                raise MARC21Exn ("Control fields are of type String")
                        else:
                                self.dataFields[tag]=value
                else:
                        if isinstance(value,MARC21DataField):
                                self.dataFields[tag]=value
                        else:
                                #-- Fields that are not control fields *MUST* have a subfield.
                                #-- Thus, the proper assignment is {'subfield1':'data1',...}
                                #-- ie. {'a','Proper Title'}
                                raise MARC21Exn ("Data fields must be of type MARC21DataField")

        def __repr__(self):
                return self.__str__()

        def __str__(self):
                #-- Serialize all of the data fields and build the directory.
                data=""
                directory={}
                sortedFields=self.dataFields.keys()
                sortedFields.sort()
                for field in sortedFields:
                        if type(self.dataFields[field])==type([]):
                                contentList=self.dataFields[field]
                        else:
                                contentList=[self.dataFields[field]]
                        for content in contentList:
                                offset=len(data)
                                if field[:2]=='00':
                                        serializedField=str(content)+MARC21Record.FIELD_TERMINATOR
                                else:
                                        serializedField='%s'%(content)
                                length=len(serializedField)
                                if directory.has_key(field):
                                        directory[field].append((length,offset))
                                else:
                                        directory[field]=[(length,offset)]
                                data=data+serializedField

                #-- Add the record terminator.
                data=data+MARC21Record.RECORD_TERMINATOR

                #-- Now, serialize the directory.
                directoryData=""
                for field in sortedFields:
                        for directoryEntry in directory[field]:
                                length,offset=directoryEntry
                                directoryData=directoryData+"%3s%04d%05d"%(field[:3],length,offset)
                directoryData=directoryData+MARC21Record.FIELD_TERMINATOR
                
                recordLength=24+len(directoryData)+len(data)
                baseAddressOfData=24+len(directoryData)
                leaderData="%05d"%(recordLength)
                leaderData=leaderData+self.record_status[:1]
                leaderData=leaderData+self.type_of_record[:1]
                leaderData=leaderData+self.implementation_defined1[:2]
                leaderData=leaderData+self.character_coding_scheme[:1]
                leaderData=leaderData+"%01d"%(self.indicator_count)
                leaderData=leaderData+"%01d"%(self.subfield_code_length)
                leaderData=leaderData+"%05d"%(baseAddressOfData)
                leaderData=leaderData+self.implementation_defined2[:3]
                leaderData=leaderData+self.entry_map[:4]

                return leaderData+directoryData+data

        def html(self):
            from cStringIO import StringIO
            f = StringIO()
            MARC21HtmlPrint(self, f)
            return f.getvalue()


class MARC21ControlField:

        def __init__(self,data=None):
                self.raw_data=data
        
        def __str__(self):
                return self.raw_data

class MARC21DataField:
        SUBFIELD_DELIMITER=chr(31)
        ESCAPE_CHAR=chr(27)
        
        def __init__(self,record,tag,data=None):
                self.record=record
                self.tag=tag
                self.raw_data=data
                self.indicator1=' '
                self.indicator2=' '
                self.contents={}
		self.subfield_sequence = []
                
                if data is not None:
                        self.parse(data)

        def warn (self, msg):
                self.record.warn ("field %s: %s" % (self.tag,msg))

        def err (self, msg):
                self.record.err ("field %s: %s" % (self.tag,msg))

        def subfields(self):
                return self.contents.keys()

        def __getitem__(self,subfield):
                return self.contents[subfield]

        def get_elt (self, elt_id, default=NoDefault):
                vals = self.contents.get (elt_id, [])
                nvals = len (vals)
                if nvals == 0:
                        if default is not NoDefault:
                                return default
                        else:
                                self.err ("no value for element %s" % elt_id)
                elif nvals == 1:
                        return vals[0]
                else:
                        self.err ("more than one value for element %s" % elt_id)

        def get_elts (self, elt_id):
                return self.contents.get (elt_id, [])

        def __setitem__(self,subfield,value):
                self.contents[subfield]=value

        def parse(self,data):
                #-- Read the indicators.
                self.indicator1=data[0]
                self.indicator2=data[1]
                data=data[3:]
                #-- Strip the FIELD_DELIMITER
                data=data[:-1]

                while len(data)>0:
                        SDindex=string.find(data,MARC21DataField.SUBFIELD_DELIMITER)
                        if SDindex<0:
                                SDindex=len(data)
                        subfieldData=data[:SDindex]
                        data=data[SDindex+1:]
                        elt_id = subfieldData[0]
                        raw_elt_contents = subfieldData[1:]
                        elt_contents = None
                        if is_pure_ascii_graphic (raw_elt_contents):
                                # simple, efficient upgrade
                                elt_contents = unicode (raw_elt_contents, "ascii")
                        else:
                                elt_contents = marc8_to_unicode (raw_elt_contents)
                        self.contents.setdefault(elt_id, []).append(elt_contents)
			self.subfield_sequence.append((elt_id, elt_contents))

        def __str__(self):
                data=self.indicator1[0]+self.indicator2[0]
                sortedSubfields=self.contents.keys()
                sortedSubfields.sort()
                for subfield in sortedSubfields:
                        if type(self.contents[subfield])==type([]):
                                contentList=self.contents[subfield]
                        else:
                                contentList=[self.contents[subfield]]
                        for content in contentList:
                                data=data+MARC21DataField.SUBFIELD_DELIMITER+subfield+content
                data=data+MARC21Record.FIELD_TERMINATOR
                return data

class MARC21File:
        def __init__(self,source):
                self.index=[0]
                self.current=0
                if type(source) is str:
                        self.sourceFile=open(source, "rb")
                else:
                        self.sourceFile=source

        def __del__(self):
                self.sourceFile.close()

        def next(self):
                record_pos = self.sourceFile.tell()
                data=self.sourceFile.read(5)
                if data=="":
                        return None
                else:
                        recordLength=int(data)
                        data=data+self.sourceFile.read(recordLength-5)
                        #self.current=self.current+1
                        #self.index.append(self.sourceFile.tell())
                        return MARC21Record(data,record_pos)
        
        def rewind(self, n=1):
                self.current=self.current-n
                if self.current<0:
                        self.current=0
                self.sourcefile.seek(self.index[self.current])

def isControlFieldTag(tag):
        if tag[:2]=='00':
                return 1
        else:
                return 0

import sys
def MARC21PrettyPrint(M, outfile=None):
	outfile = outfile or sys.stdout
        sortedFields=M.fields()
        sortedFields.sort()
        for field in sortedFields:
                contentList=[]
                if type(M[field])==type([]):
                        contentList=M[field]
                else:
                        contentList=[M[field]]
                for content in contentList:
                        print >>outfile, field
                        if isControlFieldTag(field):
                                print >>outfile, '\t%s'%(content)
                        else:
                                subfields=content.subfields()
                                subfields.sort()
                                for subfield in subfields:
                                        if type(content[subfield])==type([]):
                                                subfieldContentList=content[subfield]
                                        else:
                                                subfieldContentList=[content[subfield]]
                                        for subfieldContent in subfieldContentList:
                                                print >>outfile, '\t%s : %s'%(subfield,subfieldContent.encode ('utf8'))

def xlist(x):
    return ((type(x) is list and x) or [x])

def sp(c):
    return ((c==' ' and '&nbsp;') or c)

from unicodedata import normalize

def MARC21HtmlPrint(M, outfile=None):
    outfile = outfile or sys.stdout
    for field in sorted(M.fields()):
        for content in xlist(M[field]):
	    print >>outfile, '<large>%s</large>'% field,
	    if isControlFieldTag(field):
		print >>outfile, '<code>',
		print >>outfile, ''.join(map(sp, '%s'%(content))),
		print >>outfile, '</code>'
	    else:
		ind = [content.indicator1, content.indicator2]
		print >>outfile, '<code>%s</code>'% normalize('NFKC', unicode(''.join(map(sp, ind))))
		# print >>outfile, '<code>%s</code>'% ''.join(map(sp, ind))

		for subfield,subfieldContent in content.subfield_sequence:
		    print >>outfile, '<code><b>$%s</b>%s</code>'%(subfield,subfieldContent.encode ('utf8'))
	    print >>outfile, '<br/>'

re_pure_ascii_graphic = re.compile ("^[ -~]*$")

def is_pure_ascii_graphic (s):
        return re_pure_ascii_graphic.match (s)

def is_pure_graphic (s):
        for c in s:
                o = ord(c)
                if 32 <= o <= 126:
                        pass
                elif 161 <= o <= 254:
                        pass
                else:
                        return False
        return True
