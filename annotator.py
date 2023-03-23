# -*- coding: utf-8 -*-
from curses import meta
from fileinput import filename
from multiprocessing import context
from typing import Tuple
import pandas as pd
import io
import os
import re
import ast
import json
from urllib.request import urlopen
from urllib.parse import urlparse, unquote
from dateutil.parser import parse
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

sub_classes = prepareQuery(
    "SELECT ?entity WHERE {?entity rdfs:subClassOf* ?parent}"
    )


def get_entities_with_property_with_value(graph, property, value):
    return [s for s, p, o in graph.triples((None,  property, value))]


units_graph = Graph()
units_graph.parse(QUDT_UNIT_URL, format='turtle')

def get_data(uri=''):
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

class CSV_Annotator():
    def __init__(self, separator: str='auto', header_separator: str= 'auto', encoding: str='auto') -> (str, json) : 
        self.separator = separator
        self.header_separator = header_separator
        self.encoding = encoding
        self.json_ld_context = [
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
        self.umlaute_dict = {
            '\u00e4': 'ae',  # U+00E4	   \xc3\xa4
            '\u00f6': 'oe',  # U+00F6	   \xc3\xb6
            '\u00fc': 'ue',  # U+00FC	   \xc3\xbc
            '\u00c4': 'Ae',  # U+00C4	   \xc3\x84
            '\u00d6': 'Oe',  # U+00D6	   \xc3\x96
            '\u00dc': 'Ue',  # U+00DC	   \xc3\x9c
            '\u00df': 'ss',  # U+00DF	   \xc3\x9f
        }
        self.superscripts_replace = {
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
    def process_web_ressource(self, url) -> dict:
        '''
        :return: returns a filename and content(json string dump) of a metafile in the json format.
        '''
        self.url=url
        self.file_data, self.file_name = get_data(url)

        if self.file_name is None or self.file_data is None:
            return "error", "cannot parse url"

        if self.encoding == 'auto':
            self.encoding = self.get_encoding(self.file_data)
            if self.encoding=='ISO-8859-1':
                self.encoding='latin-1'

        if self.separator == 'auto':
            separator = self.get_column_separator(self.file_data)
            if not separator:
                return "error", 'cant find separator, pls manualy select'
            else:
                self.separator=separator
                
        #print(url,self.separator, self.header_separator, self.encoding, self.include_table_data)
        result = self.process_file(self.file_name, self.file_data, self.separator, self.header_separator, self.encoding, self.url.rsplit(self.file_name,1)[0])
        return result

    def get_encoding(self, file_data):
        """

        :param file_data:   content of the file we want to parse
        :return:            encoding of the specified file content e.g. utf-8, ascii..
        """
        result = chardet.detect(file_data)
        return result['encoding']

    def get_column_separator(self, file_data: bytes, rownum = None):
        """

        :param file_data: data of the file we want to parse
        :param rownum: index of row ind data to test, if None uses last one by default
        :return:          the seperator of the specified data, e.g. ";" or ","
        """
        file_io = io.BytesIO(file_data)
        if rownum != None:
            test_line=file_io.readlines()[rownum]
        else:
            file_io.seek(-2048,os.SEEK_END)
            test_line=file_io.readlines()[-1]
        #print(test_line.decode(self.encoding))
        sniffer = Sniffer()
        try:
            dialect = sniffer.sniff(test_line.decode(self.encoding),delimiters=[";","\t","|"])
            return dialect.delimiter
        except:
            try:
                dialect = sniffer.sniff(test_line.decode(self.encoding))
                return dialect.delimiter
            except: 
                return None
        

    # define generator, which yields the next count of
    # occurrences of separator in row
    def generate_col_counts(self, file_data, separator, encoding):
        sep_regex = re.compile(separator.__str__())
        with io.StringIO(file_data.decode(encoding)) as f:
            row = f.readline()
            while (row != ""):
                # match with re instead of count() function!
                yield len(sep_regex.findall(row)) + 1
                row = f.readline()
            return

    def get_table_charateristics(self, file_data: bytes, separator: str, encoding: str) -> (int, int):
        """
        This method finds the beginning of a header line inside a csv file,
        aswell as the number of columns of the datatable
        :param file_data: content of the file we want to parse as bytes
        :param separator_string: csv-separator, will be interpretet as a regex
        :param encoding: text encoding
        :return: a 2-tuple of (counter, num_cols)
                      where
                          counter : index of the header line in the csv file
                          num_cols : number of columns in the data-table
        """
        last_line = b''
        num_cols = 0
        sep_regex = re.compile(separator.__str__())

        with io.BytesIO(file_data) as f:

            f.seek(-2, os.SEEK_END)

            cur_char = f.read(1)

            # edgecase that there is no \n at the end of file
            if(cur_char != b'\n'):
                cur_char = f.read(1)

            while(cur_char == b'\n' or cur_char == b'\r'):
                f.seek(-2, os.SEEK_CUR)
                cur_char = f.read(1)

            while cur_char != b'\n':
                last_line = cur_char + last_line
                f.seek(-2, os.SEEK_CUR)
                cur_char = f.read(1)

            num_cols = len(sep_regex.findall(
                last_line.decode(encoding))) + 1

        # iter over column counts from end of file, if column count changes start of data table reached
        col_counts=list(enumerate(self.generate_col_counts(file_data=file_data, separator=separator, encoding=encoding)))
        #max_cols=col_counts[-1][1]
        runs=0
        col_counts.reverse()
        for rownum, count in col_counts:
            if runs==0:
                max_cols=count
            if count!=max_cols:
                return rownum+1, max_cols
            runs+=1
        return 0, max_cols

    def get_num_header_rows_and_dataframe(self, file_data, separator_string, header_length, encoding):
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
        file_string = io.StringIO(file_data.decode(encoding))
        #skip lines already processed
        num_header_rows=0
        counter=0
        for row in range(header_length):
            file_string.readline()
        for line in file_string:
            tests=[self.get_value_type(
                string)[0] in ['BLANK', 'TEXT'] for string in line.split(separator_string)]
            all_text = all(tests)
            if all_text:
                counter += 1
                continue
            else:
                num_header_rows=counter
                break
        #print(num_header_rows,list(range(num_header_rows)))
        file_string.seek(0)
        try: 
            table_data = pd.read_csv(file_string, header= list(range(num_header_rows)), sep=separator_string,
            skiprows=header_length, encoding=encoding)
        except:
            table_data=pd.DataFrame()
        return num_header_rows, table_data

    def get_unit(self, string):
        # remove possible braces
        string=string.strip(" []():")
        #get rid of superscripts
        for k in self.superscripts_replace.keys():
            string = string.replace(k, self.superscripts_replace[k])
        #print(string)
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

    def is_date(self, string, fuzzy=False):
        try:
            parse(string, fuzzy=fuzzy)
            return True

        except ValueError:
            return False

    def get_value_type(self, string: str)-> Tuple:
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
            if self.is_date(string):
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

    def describe_value(self, value_string):
        #remove leading and trailing white spaces
        if pd.isna(value_string):
            return {}
        val_type=self.get_value_type(value_string)
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
            return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': str(parse(value_string).isoformat()), '@type': str(val_type[1])}}
        else:
            return {
                "@type": "oa:TextualBody",
                "oa:purpose": "oa:tagging",
                "oa:format": "text/plain",
                "oa:value": value_string.strip()
            }
                #return {"@type": "qudt:QuantityValue",'qudt:value': {'@value': value_string, '@type': 'xsd:string'}}

    def make_id(self, string, filename=None):
        for k in self.umlaute_dict.keys():
            string = string.replace(k, self.umlaute_dict[k])
        if filename:
            return filename + '/' + re.sub('[^A-ZÜÖÄa-z0-9]+', '', string.title().replace(" ", ""))
        else:
            return re.sub('[^A-ZÜÖÄa-z0-9]+', '', string.title().replace(" ", ""))

    def get_additional_header(self, file_data: bytes, header_lenght: int = 0, header_separator='auto', encoding: str = 'utf-8') -> pd.DataFrame: 
        """

        :param file_data: content of the file we want to parse
        :param header_lenght: lenght of the additional header at start of csv file in count of rows
        :param encoding: text encoding
        :return:
        """
        if header_lenght:
            #test the last additional header line for the separator
            if header_separator=='auto':
                header_separator = self.get_column_separator(file_data, rownum=header_lenght-1)
            #find max colum count
            gen=self.generate_col_counts(file_data=file_data, separator=header_separator, encoding=encoding)
            col_count=list(next(gen) for rows in range(header_lenght))
            #print(col_count)
            #print(header_lenght, header_separator)
            file_string = io.StringIO(file_data.decode(encoding))
            header_df = pd.read_csv(file_string, header=None, sep=header_separator, nrows=header_lenght,
                                      names=range(max(col_count)),
                                      encoding=encoding,
                                      skip_blank_lines=False)
            header_df['row'] = header_df.index
            header_df.rename(columns={0: 'param'}, inplace=True)
            header_df.set_index('param', inplace=True)
            header_df = header_df[~header_df.index.duplicated()]
            header_df.dropna(thresh=2, inplace=True)
            #print(header_df)
            return header_df

        else:
            return None

    def serialize_header(self, header_data, filename=None):
        params = list()
        info_line_iri = "oa:Annotation"
        for parm_name, data in header_data.to_dict(orient='index').items():
            # describe_value(data['value'])
            # try to find unit if its last part and separated by space in label
            #print(parm_name, data)
            body=list()
            #remove : if any at end
            if parm_name[-1]==":":
                parm_name=parm_name[:-1]
            #see if there is a unitstring in the param name
            if len(parm_name.split(' ')) > 1:
                unit_json = self.get_unit(parm_name.rsplit(' ',1)[-1])
            else:
                unit_json = {}
            if unit_json:
                #print('unit in param name',unit_json)
                parm_name=parm_name.rsplit(' ', 1)[0]
            para_dict = {'@id': self.make_id(parm_name,filename)+str(
                data['row']), 'label': parm_name.strip(), '@type': info_line_iri}
            for col_name, value in data.items():
                value=str(value)
                #print(body)
                #print(parm_name,col_name, value,type(value))
                if col_name == 'row':
                    para_dict['rownum'] = {
                        "@value": data['row'], "@type": "xsd:integer"}
                else:
                    to_test=value
                    #test space separated parts for beeing unit strings
                    for part in to_test.split(' '):
                        unit_dict = self.get_unit(part.strip())
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
                    #print(to_test,value,unit_json)
                    if to_test:
                        toadd=self.describe_value(to_test)
                        if toadd.get('@type') == 'qudt:QuantityValue':
                            toadd={**toadd,**unit_json}
                        else:
                            # should result in textual body
                            toadd=self.describe_value(value)
                if toadd:
                        body.append(toadd)
                        toadd={}
            #print(body)
            para_dict['oa:hasBody']=body
            params.append(para_dict)
        # print(params)
        return params

    def process_file(self, file_name, file_data, separator, header_separator, encoding, file_domain='') -> dict:
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

        metadata_csvw = dict()
        metadata_csvw["@context"] = self.json_ld_context        

        meta_file_name = file_name.split(sep='.')[0] + '-metadata.json'
        metadata_url='{}/{}'.format(file_domain,meta_file_name)
        
        metadata_csvw["@id"]=metadata_url
        if self.url:
            metadata_csvw["url"] = self.url
        else:
            metadata_csvw["url"] = file_name
        
        data_table_header_row_index, data_table_column_count = self.get_table_charateristics(
            file_data, separator, encoding)
        # read additional header lines and provide as meta in results dict
        if data_table_header_row_index != 0:
            header_data = self.get_additional_header(
                file_data, data_table_header_row_index, header_separator,encoding)
            #print(header_data)
            if not header_data.empty:
                # print("serialze additinal header")
                metadata_csvw["notes"] = self.serialize_header(
                    header_data, filename=None)
        # read tabular data structure, and determine number of header lines for column description used
        header_lines, table_data = self.get_num_header_rows_and_dataframe(
            file_data, separator, data_table_header_row_index, encoding)
        # describe dialect
        metadata_csvw["dialect"] = {"delimiter": separator,
                                    "skipRows": data_table_header_row_index, "headerRowCount": header_lines, "encoding": encoding}
        # describe columns
        #print([(string, self.get_value_type(string)) for string in line.split(separator_string)])
        table_schema = self.describe_table(table_data)
        metadata_csvw['tableSchema'] = table_schema
        return {'filename':meta_file_name, 'filedata': metadata_csvw}
    def describe_table(self, table_data: pd.DataFrame)-> dict:
        table_schema=dict()
        if not table_data.empty:
            column_json = list()
            #adding an index identifier
            json_str={"name": "GID",
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
                    titles_list=[*titles]
                else:
                    titles_list=[titles,]
                name_str=self.make_id(titles_list[0])
                for title in titles_list:
                    titleparts=title.split(' ')
                    for part in titleparts:
                        unit_dict=self.get_unit(part)
                        if unit_dict:
                            break
                titles_list.append(name_str)
                json_str = {
                    **{
                        'titles': titles_list,
                        '@id': name_str,
                        'name': name_str,
                        #'aboutUrl': "#gid-{GID}-"+name_str
                    },
                    **unit_dict
                }
                if unit_dict:
                    json_str['@type']=["Column","qudt:QuantityValue"]
                else:
                    json_str['@type']=["Column"]
                #print(titles_list,column_types[colnum])
                xsd_format=self.get_value_type(table_data.iloc[1][colnum])[1]
                if xsd_format:
                    json_str['format'] = {'@id': xsd_format}
                column_json.append(json_str)
            table_schema = {"columns": column_json}
            table_schema["primaryKey"] = column_json[0]['name']
            table_schema["aboutUrl"] = "#gid-{GID}"
            # table_schema["propertyUrl"] = "schema:value"
        return table_schema

    def set_encoding(self, new_encoding: str):
        self.encoding = new_encoding

    def set_separator(self, new_separator: str):
        self.separator = new_separator
