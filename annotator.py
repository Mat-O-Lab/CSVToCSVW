# -*- coding: utf-8 -*-
from typing import Tuple
import pandas as pd
import io
import os
import re
import ast
import json
from urllib.request import urlopen
from urllib.parse import urlparse, unquote
from dateutil.parser import parse as date_parse
from csv import Sniffer

import chardet
import locale
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, XSD, CSVW, DC, PROV
from rdflib.plugins.sparql import prepareQuery

QUDT_UNIT_URL = './ontologies/qudt_unit.ttl'
QUDT = Namespace("http://qudt.org/schema/qudt/")
QUNIT = Namespace("http://qudt.org/vocab/unit/")

UMLAUTE = {
            '\u00e4': 'ae',  # U+00E4	   \xc3\xa4
            '\u00f6': 'oe',  # U+00F6	   \xc3\xb6
            '\u00fc': 'ue',  # U+00FC	   \xc3\xbc
            '\u00c4': 'Ae',  # U+00C4	   \xc3\x84
            '\u00d6': 'Oe',  # U+00D6	   \xc3\x96
            '\u00dc': 'Ue',  # U+00DC	   \xc3\x9c
            '\u00df': 'ss',  # U+00DF	   \xc3\x9f
        }
REPLACE_SUPERSCRIPTS = {
            #'\u2070':°,
            '\u00b9':'',
            '\u00b2':'2',
            '\u00b3':'3',
            '\u2074':'4',
            '\u2075':'5',
            '\u2076':'6',
            '\u2077':'7',
            '\u2078':'8',
            '\u2079':'9',
            '\u00b0C':'Cel', #for °C
        }

# the order is importent
SEPARATORS_REGEX = [ r";", r"\|", r":+\s+\s*", r"\t", r","]

sub_classes = prepareQuery(
    "SELECT ?entity WHERE {?entity rdfs:subClassOf* ?parent}"
    )


def get_entities_with_property_with_value(graph, property, value):
    return [s for s, p, o in graph.triples((None,  property, value))]


units_graph = Graph()
units_graph.parse(QUDT_UNIT_URL, format='turtle')

def get_data(uri='')-> (bytes, str):
    try:
        uri_parsed = urlparse(uri)
    except:
        print('not an uri - if local file add file:// as prefix')
        return None
    else:
        filename = unquote(uri_parsed.path).rsplit('/download/upload')[0].split('/')[-1]
        #print(uri,filename)
        if uri_parsed.scheme in ['https', 'http']:
            filedata = urlopen(uri).read()

        elif uri_parsed.scheme == 'file':
            filedata = open(unquote(uri_parsed.path), 'rb').read()
        else:
            print('unknown scheme {}'.format(uri_parsed.scheme))
            return None
        return filedata, filename

def is_date(string, fuzzy=False)->bool:
    try:
        date_parse(string, fuzzy=fuzzy)
        return True

    except ValueError:
        return False

def make_id(string, filename=None)-> str:
    for k in UMLAUTE.keys():
        string = string.replace(k, UMLAUTE[k])
    if filename:
        return filename + '/' + re.sub('[^A-ZÜÖÄa-z0-9]+', '', string.title().replace(" ", ""))
    else:
        return re.sub('[^A-ZÜÖÄa-z0-9]+', '', string.title().replace(" ", ""))

def get_value_type(string: str)-> Tuple:
    string = str(string)
    # remove spaces and replace , with . and
    string = string.strip().replace(',', '.')
    if len(string) == 0:
        return 'BLANK', None
    try:
        t = ast.literal_eval(string)
    except ValueError:
        return 'TEXT', XSD.string
    except SyntaxError:
        if is_date(string):
            return 'DATE', XSD.dateTime
        else:
            return 'TEXT', XSD.string
    else:
        if type(t) in [int, float, bool]:
            if type(t) is int:
                return 'INT', XSD.integer
            if t in set((True, False)):
                return 'BOOL', XSD.boolean
            if type(t) is float:
                return 'FLOAT', XSD.double
        else:
            #return 'TEXT'
            return 'TEXT', XSD.string

def get_encoding(file_data: bytes)-> str:
    """

    :param file_data:   content of the file we want to parse
    :return:            encoding of the specified file content e.g. utf-8, ascii..
    """
    result = chardet.detect(file_data)
    return result['encoding']

def get_unit(string) -> dict:
    # remove possible braces
    string=string.strip(" []():")
    #get rid of superscripts
    for k in REPLACE_SUPERSCRIPTS.keys():
        string = string.replace(k, REPLACE_SUPERSCRIPTS[k])
    string=string.replace('N/mm2','MPa')
    string=string.replace('Nm','N.m')
    string=string.replace('sec','s')
    
    found = get_entities_with_property_with_value(
            units_graph, QUDT.symbol, Literal(string)) \
            + get_entities_with_property_with_value(
                units_graph, QUDT.ucumCode,
                Literal(string, datatype=QUDT.UCUMcs)
                )
    # will only look up qudt now, seams more mature
    if found:
        return {"qudt:unit": {"@id": str(found[0]), "@type": units_graph.value(found[0], RDF.type)}}
    else:
        return {}


def get_column_separator(regex_list: list,line: str)-> (str, int):
    del_counts = {}
    # count the number of occurrences of each delimiter regex in the line
    for regex in regex_list:
        sep_regex = re.compile(regex.__str__())
        count = len(re.findall(sep_regex, line))
        del_counts[regex] = count
    # choose the delimiter regex with the highest count
    mvp_del_regex = max(del_counts, key=del_counts.get)
    # extract the delimiter character from the regex
    search=re.search(mvp_del_regex, line)
    #mvp_del = re.search(mvp_del_regex, line).group()
    if not search:
        return None, None
    results, count=mvp_del_regex, del_counts[mvp_del_regex]
    #cover case that all in line are float of german notation (,), select the second best of only one occurency less
    if mvp_del_regex==',':
        #find second best
        del_counts.pop(',')
        second_best_regex=max(del_counts, key=del_counts.get)
        if del_counts[second_best_regex]>=count-1:
            results=second_best_regex
            count=del_counts[second_best_regex]
    return results, count

def describe_value(value_string: str)-> dict:
    #remove leading and trailing white spaces
    if pd.isna(value_string):
        return {}
    val_type=get_value_type(value_string)
    if val_type[0] == 'INT':
        return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': int(value_string), '@type': str(val_type[1])}}
    elif val_type[0] == 'BOOL':
        return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': bool(value_string), '@type': str(val_type[1])}}
    elif val_type[0] == 'FLOAT':
        if isinstance(value_string,str):
            #replace , with . as decimal separator
            value_string = value_string.strip().replace(',', '.')
        return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': float(value_string), '@type': str(val_type[1])}}
    elif val_type[0] == 'DATE':
        return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': str(date_parse(value_string).isoformat()), '@type': str(val_type[1])}}
    else:
        return {
            "@type": "oa:TextualBody",
            "oa:purpose": "oa:tagging",
            "oa:format": "text/plain",
            "oa:value": value_string.strip()
        }
            #return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': value_string, '@type': 'xsd:string'}}


class CSV_Annotator():
    def __init__(self, url: str, encoding: str='auto') -> (str, json) : 
        self.url=url
        self.encoding = encoding
        self.context = [
            "http://www.w3.org/ns/csvw", {
                #"mseo": "https://purl.matolab.org/mseo/mid/",
                "oa": "http://www.w3.org/ns/oa#",
                "label": "http://www.w3.org/2000/01/rdf-schema#label",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
                "qudt": "http://qudt.org/schema/qudt/",
                "dc": str(DC),
                "prov": str(PROV),
                }
        ]
        self.parts = list()
        self.file_name=''
        self.file_domain=''
        self.file_string=''
        
        self.file_name, self.encoding, self.file_string=self.read_data(self.url, self.encoding)
        self.file_domain=self.url.rsplit(self.file_name,1)[0]
        self.meta_file_name = self.file_name.split(sep='.')[0] + '-metadata.json'
        
        self.parts=self.__segment_csv(self.file_string)

    @staticmethod
    def read_data(url, encoding: str)->(str,str,str):
        file_data, file_name = get_data(url)
        if file_name is None or file_data is None:
            return "error", "cannot parse url"

        if encoding == 'auto':
            encoding = get_encoding(file_data)
            if encoding=='ISO-8859-1':
                encoding='latin-1'
        file_string=file_data.decode(encoding)
        return file_name, encoding, file_string
    def annotate(self) -> dict:
        '''
        :return: returns a filename and content(json string dump) of a metafile in the json format.
        '''
        #print(url,self.separator, self.header_separator, self.encoding, self.include_table_data)
        result = self.process_data()
        return result
    
    def __str__(self):
        attrs = dict(vars(self))
        attrs.pop('file_string', None)
        return str(attrs)
    
    @staticmethod
    def __segment_csv(file_string: str)->dict:
        segments = []
        parts={0:{}}
        i=0
        s_start=0
        s_end=0
        prev=None
        with io.StringIO(file_string) as f:
            for line in f:
                current=get_column_separator(SEPARATORS_REGEX,line.rstrip())
                if prev is not None and current and current != prev:
                    segments.append({'start': s_start, 'end': i, 'sep': prev[0], 'count': prev[1]})
                    s_start=i
                else:
                    s_end=i
                prev = current
                i+=1
            #add last segment aswell
            s_end=i
            segments.append({'start': s_start, 'end': s_end, 'sep': prev[0], 'count': prev[1]})
            #if segments have only one line and no header row mark them additional_header
            parts={}
            last_part=None
            #joint segments in parts if possible
            for segment in segments:        
                if last_part is not None:
                    #update last part to overlab segment
                    if last_part['sep']==segment['sep'] and  last_part['count']==segment['count']:
                        last_part['end']=segment['end']
                    else:
                        if not parts.keys():
                            part_num=0
                        else:
                            part_num=max(parts.keys())+1
                        parts[part_num]={'start': segment['start'], 'end': segment['end'], 'sep':segment['sep'], 'count': segment['count'], 'type': 'unknown'}
                else:
                    if not parts.keys():
                            part_num=0
                    else:
                        part_num=max(parts.keys())+1
                    parts[part_num]={'start': segment['start'], 'end': segment['end'], 'sep':segment['sep'], 'count': segment['count'], 'type': 'unknown'}
                if parts.keys():
                    last_part=parts[max(parts.keys())]
            #test lenght of segments and first line of parts to be all text to categorize to meta or data table part
            parts={key: value for key,value in parts.items() if value['sep']}
            for key, value in parts.items():
                f.seek(0)
                if value['end']-value['start']==1 or value['sep']==':+\\s+\\s*':
                    value['type']='meta'
                #test for header line but not if sep ':+\\s+\\s*' should be config style data which is meta
                elif value['sep']!=':+\\s+\\s*' and value['end']-value['start']>=1:
                    for i, line in enumerate(f):
                        if i==value['start']:
                            tests=[get_value_type(string)[0] in ['BLANK', 'TEXT', 'INT'] for string in re.split(value['sep'],line)]
                            all_text = all(tests)
                            break
                    if all_text:
                        #seams it has at least on header row
                        value['type']='data'
        return parts
    
    @staticmethod 
    def __get_data_meta_part(file_data: str, start: int , end: int , col_count: int, separator: str) -> pd.DataFrame: 
        """

        :param file_data: content of the file we want to parse
        :param header_lenght: lenght of the additional header at start of csv file in count of rows
        :param encoding: text encoding
        :return:
        """
        file_string = io.StringIO(file_data)
        #skip to segement start
        if start>0: 
            for i,line in enumerate(file_string):
                if i==(start-1):
                    break
        
        header_df = pd.read_csv(file_string, header=None, sep=separator, nrows=end-start,
                                    names=range(col_count),
                                    #encoding=encoding,
                                    skip_blank_lines=False,
                                    engine='python')
        header_df['row'] = header_df.index
        header_df.rename(columns={0: 'param'}, inplace=True)
        header_df.set_index('param', inplace=True)
        header_df = header_df[~header_df.index.duplicated()]
        header_df.dropna(thresh=2, inplace=True)
        return header_df
    
    @staticmethod
    def __get_data_table_part(file_data, start: int , end: int , separator: str):
        """

        :param file_data: content of the file we want to parse
        :param separator_string: csv-delimiter
        :param header_length: rows of the header
        :param encoding: csv-encoding
        :return: 2-tuple (num_header_rows, table_data)
                      where
                          num_header_rows : number of header rows
                          table_data : pandas DataFrame object containing the tabular information
        """
        #print(separator_string, header_length, encoding)
        file_string = io.StringIO(file_data)
        #skip lines already processed
        num_header_rows=0
        counter=0
        if start>0: 
            for i,line in enumerate(file_string):
                if i==(start-1):
                    break
        for line in file_string:
            tests=[get_value_type(string)[0] in ['BLANK', 'TEXT', 'INT'] for string in re.split(separator ,line)]
            all_text = all(tests)
            if all_text:
                counter += 1
                continue
            else:
                num_header_rows=counter
                break
        file_string.seek(0)
        # skip to start of part
        if start>0: 
            for i,line in enumerate(file_string):
                if i==(start-1):
                    break
        table_data = pd.read_csv(file_string,
                                 header= list(range(num_header_rows)),
                                 sep=separator,
                                 nrows=end-start-num_header_rows,
                                 #encoding=encoding,
                                 engine='python')
        return num_header_rows, table_data
    
    @staticmethod
    def __serialize_meta(header_data, row_offset: int=0, filename=None):
        params = list()
        info_line_iri = "oa:Annotation"
        for parm_name, data in header_data.to_dict(orient='index').items():
            # describe_value(data['value'])
            # try to find unit if its last part and separated by space in label
            body=list()
            #remove : if any at end
            if parm_name[-1]==":":
                parm_name=parm_name[:-1]
            #see if there is a unitstring in the param name
            if len(parm_name.split(' ')) > 1:
                unit_json = get_unit(parm_name.rsplit(' ',1)[-1])
            else:
                unit_json = {}
            if unit_json:
                parm_name=parm_name.rsplit(' ', 1)[0]
            para_dict = {'@id': make_id(parm_name,filename)+str(
                data['row']+row_offset), 'label': parm_name.strip('"'), '@type': info_line_iri}
            for col_name, value in data.items():
                value=str(value).strip('"')
                if col_name == 'row':
                    para_dict['rownum'] = {
                        "@value": data['row']+row_offset, "@type": "xsd:integer"}
                else:
                    to_test=value
                    #test space separated parts for beeing unit strings
                    for part in to_test.split(' '):
                        unit_dict = get_unit(part.strip())
                        if unit_dict:
                            unit_json=unit_dict
                            #if string is a number unit will be NUM, then dont strip unit of string
                            if unit_dict['qudt:unit']['@id']!='http://qudt.org/vocab/unit/NUM':
                                to_test=to_test.replace(part,'').strip()
                            if not to_test:
                                #empty string -> add unit if there was aquantity value detected in the row before
                                if any(entry.get('@type') == 'qudt:QuantityValue' for entry in body):
                                    for entry in body:
                                        #print('updating entry')
                                        if entry.get('@type') == 'qudt:QuantityValue':
                                            entry.update({**entry,**unit_dict})
                                            toadd={}
                            break
                    if value in ['nan','None']:
                        continue
                    #first test rest of to_test for beeing a value, if add a quantity value - not add textual body
                    if to_test:
                        toadd=describe_value(to_test)
                        if toadd.get('@type') == 'qudt:QuantityValue':
                            toadd={**toadd,**unit_json}
                        else:
                            # should result in textual body
                            toadd=describe_value(value)
                if toadd:
                        body.append(toadd)
                        toadd={}
            para_dict['oa:hasBody']=body
            params.append(para_dict)
        return params

    @staticmethod
    def __describe_table(table_data: pd.DataFrame, about_prefix: str='')-> dict:
        table_schema=dict()
        if not table_data.empty:
            column_json = list()
            #adding an index identifier
            json_str={
                "@id": about_prefix+"-GID",
                "name": "GID",
                "titles": [
                    "GID",
                    "Generic Identifier"
                ],
                #"dc:description": "An identifier as index of a table.",
                "datatype": "string",
                "required": True,
                "suppressOutput": True,
                # "propertyUrl": "schema:url",
                # "valueUrl": "gid-{GID}"
                "@type": "Column"
            }
            column_json.append(json_str)
            for colnum, titles in enumerate(table_data.columns):

                if isinstance(titles,Tuple):
                    titles_list=[title.strip('"') for title in titles]
                else:
                    titles_list=[titles.strip('"'),]
                name_str=make_id(titles_list[0])
                for title in titles_list:
                    titleparts=title.split(' ')
                    for part in titleparts:
                        unit_dict=get_unit(part)
                        if unit_dict:
                            break
                titles_list.append(name_str)
                json_str = {
                    **{
                        'titles': titles_list,
                        '@id': about_prefix+'-'+name_str,
                        'name': name_str,
                        #'aboutUrl': "#gid-{GID}-"+name_str
                    },
                    **unit_dict
                }
                json_str['@type']=["Column"]
                xsd_format=get_value_type(table_data.iloc[1][colnum])[1]
                if xsd_format:
                    json_str['format'] = {'@id': xsd_format}
                column_json.append(json_str)
            table_schema = {"columns": column_json}
            table_schema["primaryKey"] = column_json[0]['name']
            table_schema["aboutUrl"] = "#"+about_prefix+"-gid-{GID}"
            # table_schema["propertyUrl"] = "schema:value"
        return table_schema

    def process_data(self) -> dict:
        """

        :param file_name: name of the file we want to process
        :param file_data: content of the file
        :param separator: csv-seperator /delimiter of the data table part
        :param header_separator: csv-seperator /delimiter of the additianl header that might occure before
        :param encoding:  text-encoding (e.g. utf-8..)
        :return: a 2-tuple (meta_filename,result)
                      where
                          result :    the resulting metadata on how to
                                      read the file (skiprows, colnames ..)
                                      as a json dump
                          meta_filename :  the name of the metafile we want to write
        """

        # init results dict
        #data_root_url = "https://github.com/Mat-O-Lab/resources/"

        metadata = dict()
        metadata["@context"] = self.context        
        meta_file_name = self.meta_file_name
        #metadata_csvw["@id"]=metadata_url
        metadata["@id"]=''
        metadata['@type']=CSVW.TableGroup
        metadata["notes"]=list()
        metadata["tables"]=list()
        
        if self.url:
            url_string = self.url
        else:
            url_string = self.file_name
        metadata["url"]=url_string
        #try to find all table like segments in the file
        for key, value in self.parts.items():
            if value['type']=='meta':
                meta_data=self.__get_data_meta_part(self.file_string, start=value['start'], end=value['end'], col_count=value['count']+1,separator=value['sep'])
                if not meta_data.empty:
                    metadata["notes"].extend(self.__serialize_meta(meta_data, row_offset=value['start'],filename=None))
            if value['type']=='data':
                # read tabular data structure, and determine number of header lines for column description used
                # table_data=self.get_meta_data(file_data, start=value['start'], end=value['end'], col_count=value['count']+1,header_separator=value['sep'], encoding=encoding)
                header_lines, table_data = self.__get_data_table_part(self.file_string, start=value['start'], end=value['end'], separator=value['sep'])
                if not table_data.empty:
                    table={
                        "url": url_string,
                        "dialect": {
                        "delimiter": value['sep'],
                        "skipRows": value['start'],
                        "headerRowCount": header_lines,
                        "encoding": self.encoding
                        },
                        'tableSchema': self.__describe_table(table_data, str(key))
                    }
                    metadata["tables"].append((table.copy()))

        return {'filename':meta_file_name, 'filedata': metadata}
    
    def set_encoding(self, new_encoding: str):
        self.encoding = new_encoding
