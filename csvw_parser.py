from importlib.metadata import metadata
from csvwlib.converter.ModelConverter import ModelConverter, ValuesValidator
from csvwlib.converter.ToRDFConverter import ToRDFConverter
from csvwlib.utils.url.PropertyUrlUtils import PropertyUrlUtils
from csvwlib.utils.url.UriTemplateUtils import UriTemplateUtils
from csvwlib.utils.ATDMUtils import ATDMUtils
from csvwlib.utils.json.CommonProperties import CommonProperties

from pydantic import AnyUrl
import csv as csvlib
import requests
import pandas as pd
from rdflib import BNode, URIRef, Literal
from rdflib.namespace import CSVW, RDF

from urllib.request import urlopen
from urllib.parse import urlparse, unquote
def open_file(uri=''):
        print('try to open: {}'.format(uri))
        try:
            uri_parsed = urlparse(uri)
        except:
            print('not an uri - if local file add file:// as prefix')
            return None
        else:
            filename = unquote(uri_parsed.path).split('/')[-1]
            if uri_parsed.scheme in ['https', 'http']:
                filedata = urlopen(uri).read()

            elif uri_parsed.scheme == 'file':
                filedata = open(unquote(uri_parsed.path), 'rb').read()
            else:
                print('unknown scheme {}'.format(uri_parsed.scheme))
                return None
            return filedata, filename


class CSVWtoRDF:
    def __init__(self,metadata_url: AnyUrl, csv_url: AnyUrl) -> None:
        self.metadata_url=metadata_url
        if csv_url:
            self.csv_url=csv_url
        else:
            self.csv_url=None
        converter=CSVWModelConverter(csv_url, metadata_url)
        self.atdm, self.metadata =converter.convert_to_atdm('standard')
    def convert(self):
        return RDFConverter(self.atdm, self.metadata).convert('standard','turtle')

class RDFConverter(ToRDFConverter):
    def convert(self, mode='standard', format=None):
        self.mode = mode
        main_node = BNode()
        if mode == 'standard':
            self.graph.add((main_node, RDF.type, CSVW.TableGroup))
            self._add_file_metadata(self.metadata, main_node)
        # TODO: 4.5 non-core annotations

        for table_metadata, table_data in zip(self.metadata['tables'], self.atdm['tables']):
            self._parse_table(main_node, table_metadata, table_data)

        return self.graph if format is None else self.graph.serialize(format=format)
    def _parse_row_data(self, atdm_row, subject, table_metadata, property_url, row_node, atdm_table):
        top_level_property_url = property_url
        atdm_columns = atdm_table['columns']
        for index, entry in enumerate(atdm_row['cells'].items()):
            col_name, values = entry
            for col_metadata in atdm_columns:
                if col_metadata['name'] == col_name:
                    break
            if col_metadata.get('suppressOutput', False):
                continue
            property_url = col_metadata.get('propertyUrl', top_level_property_url)
            if 'aboutUrl' in col_metadata:
                subject = CustomUriTemplateUtils.insert_value_rdf(col_metadata['aboutUrl'], atdm_row, col_name,
                                                            table_metadata['url'])
                if self.mode == 'standard':
                    self.graph.add((row_node, CSVW.describes, subject))

            property_namespace = PropertyUrlUtils.create_namespace(property_url, table_metadata['url'])
            predicate = self._predicate_node(property_namespace, property_url, col_name)
            self._parse_cell_values(values, col_metadata, subject, predicate)

from csvwlib.utils.MetadataLocator import MetadataLocator
from csvwlib.utils.metadata import MetadataValidator, non_regex_types

class CSVWModelConverter(ModelConverter):
    def __init__(self, csv_url=None, metadata_url=None):
        super().__init__()
        self.csv_url = csv_url
        self.csvs = None
        self.values_valiator = None
        self.metadata_url = metadata_url
        self.start_url = metadata_url if metadata_url is not None else csv_url
        self.metadata = None
        self.atdm = {'@type': '@AnnotatedTableGroup'}
        self.mode = 'standard'

    def _fetch_csvs(self):
        if self.metadata is None or self.metadata == {}:
            self.csvs = [parse_csv_from_url_to_list(self.csv_url)]
        else:
            if 'tables' in self.metadata:
                self.csvs = list(
                    map(lambda table:
                        parse_csv_from_url_to_list(table['url'],
                        delimiter=self._delimiter(table),
                        skiprows=self._skipRows(table),
                        num_header_rows=self._headerRowCount(table),
                        encoding=self._encoding(table),
                        ),
                    self.metadata['tables']))
            else:
                columns_names=[item['name'] for item in self.metadata["tableSchema"]["columns"] if item['name']!='GID']
                table = parse_csv_from_url_to_list(
                    self.metadata['url'],
                    delimiter=self._delimiter(self.metadata),
                    skiprows=self._skipRows(self.metadata),
                    num_header_rows=self._headerRowCount(self.metadata),
                    encoding=self._encoding(self.metadata),
                    )
                columns_names.insert(0,'GID')
                table.insert(0,columns_names)
                self.csvs=[table]
    @staticmethod
    def _skipRows(metadata):
        skipRows = 0
        if 'dialect' in metadata:
            skipRows = int(metadata['dialect'].get('skipRows', skipRows))
        return metadata.get('skipRows', skipRows)

    @staticmethod
    def _headerRowCount(metadata):
        headerRowCount = 0
        if 'dialect' in metadata:
            headerRowCount = int(metadata['dialect'].get('headerRowCount', headerRowCount))
        return metadata.get('headerRowCount', headerRowCount)
    @staticmethod
    def _encoding(metadata):
        encoding = 'utf-8'
        if 'dialect' in metadata:
            encoding = metadata['dialect'].get('encoding', encoding)
        return metadata.get('encoding', encoding)
    
    def _row_data_to_json(self, row, table_metadata):
        cells_map = {}
        null_value = table_metadata.get('null', '')
        for column_metadata, column_data in zip(table_metadata['tableSchema']['columns'], row):
            column_name = column_metadata['name']
            cells_map[column_name] = [column_data]
        return cells_map
    
    
    def convert_to_atdm(self, mode='standard'):
        """ atdm - annotated tabular data model """
        metadata_validator = MetadataValidator(self.start_url)
        self.mode = mode
        self.metadata = MetadataLocator.find_and_get(self.csv_url, self.metadata_url)
        # replace csv url in meta data if given
        if self.csv_url:
            self.metadata['url']=self.csv_url
        print(self.metadata['url'])
        self._normalize_metadata_base_url()
        self._normalize_metadata_csv_url()
        metadata_validator.validate_metadata(self.metadata)
        print('fetch table data')
        self._fetch_csvs()
        self._normalize_existing_metadata()
        self.values_valiator = ValuesValidator(self.csvs, self.metadata)
        self.values_valiator.validate()

        self._normalize_csv_values()
        print('check compartability')
        metadata_validator.check_compatibility(self.csvs, self.metadata)
        print('create table metadata')
        tables = []
        self._add_table_metadata(self.metadata, self.atdm)
        for index, table_metadata in enumerate(self.metadata['tables']):
            print(len(table_metadata['tableSchema']['columns']))
            rows = []
            start_position = self._first_row_of_data(table_metadata)
            for number, row_data in enumerate(self.csvs[index][0:], start=1):
                #print(row_data)
                source_number = number + start_position
                #print(number, source_number)
                rows.append(self._parse_row(row_data, number, source_number, table_metadata))
            tables.append({'@type': 'AnnotatedTable', 'columns': table_metadata['tableSchema']['columns'], 'rows': rows,
                           'url': table_metadata['url']})
            self._add_table_metadata(table_metadata, tables[-1])
            tables[-1] = {**table_metadata['tableSchema'], **tables[-1]}
        for table in tables:
            for column in table['columns']:
                column['@type'] = 'Column'

        self.atdm['tables'] = tables
        self._normalize_atdm_values()
        return self.atdm, self.metadata

import io

def parse_csv_from_url_to_list(csv_url,delimiter=',', skiprows=0, num_header_rows=2, encoding='utf-8'):
        print(encoding)
        file_data, file_name = open_file(csv_url)
        file_string = io.StringIO(file_data.decode(encoding))
        table_data = pd.read_csv(file_string, header= list(range(num_header_rows)), sep=delimiter, skiprows=num_header_rows+skiprows, encoding=encoding)
        # add a row index column
        #table_data.insert(0,'GID',value=range(len(table_data)))
        line_list=table_data.to_numpy().tolist()
        print(line_list[:5])
        line_list=[ [index,]+line for index, line in enumerate(line_list)]
        print(line_list[:5])
        return line_list

class CustomUriTemplateUtils(UriTemplateUtils):
    @staticmethod
    def insert_value_rdf(url, atdm_row, col_name, domain_url):
        """ Does the same what normal 'insert_value' but
        returns rdf type: URIRef of Literal based on uri"""
        filled_url = CustomUriTemplateUtils.insert_value(url, atdm_row, col_name, domain_url)
        return URIRef(filled_url) if filled_url.startswith('http') else Literal(filled_url)
    @staticmethod
    def insert_value(url, atdm_row, col_name, domain_url):
        """ Inserts value into uri template - between {...}
        If url is common property, it is returned unmodified
        Also uri is expanded with domain url if necessary """
        if CommonProperties.is_common_property(url):
            return url
        url = UriTemplateUtils.expand(url, domain_url)
        if '{' not in url:
            return url

        key = url[url.find('{') + 1:url.find('}')]
        key = key.replace('#', '')
        prefix = UriTemplateUtils.prefix(url, '')

        if key == '_row':
            return prefix + str(atdm_row['number'])
        elif key == '_sourceRow':
            return prefix + atdm_row['url'].rsplit('=')[1]
        elif key == '_name':
            return prefix + col_name
        else:
            return prefix + str(ATDMUtils.column_value(atdm_row, key))

# if self.include_table_data:
            #     #try to apply locale
            #     for column in table_data:
            #         try:
            #             table_data[column]=table_data[column].apply(locale.atof)
            #         except Exception as e:
            #             #print(e)
            #             pass
            #     #print(table_data)
            #     #serialize row of the table data
            #     columns_names=[item['name'] for item in metadata_csvw["tableSchema"]["columns"] if item['name']!='GID']
            #     #set names of colums same as in mteadata
            #     table_data.columns=columns_names
            #     table_data.insert(0,'url',data_table_header_row_index+header_lines+table_data.index)
            #     table_data.insert(1,'rownum',table_data.index)
            #     table_data.insert(2,'@id',table_data.index)
            #     table_data['@id']='gid-'+table_data['@id'].astype(str)
            #     table_data['url']=file_name+'#row='+table_data['url'].astype(str)
            #     table_entrys=[{'url': record.pop('url'), 'rownum': record.pop('rownum'), 'describes':record} 
            #         for record in table_data.to_dict('records')]
            #     metadata_csvw["row"] =table_entrys