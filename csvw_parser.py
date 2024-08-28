from typing import Tuple, List
from collections import OrderedDict
import pandas as pd
from rdflib import BNode, URIRef, Literal, Graph, Namespace
from rdflib.collection import Collection
from rdflib.util import guess_format
from rdflib.namespace import CSVW, RDF, XSD, PROV, RDFS, DC
from datetime import datetime
from urllib.request import urlopen
from urllib.parse import urlparse, unquote, quote
import io, os
import logging
import requests
from fastapi import HTTPException

QUDT_UNIT_URL = "./ontologies/qudt_unit.ttl"
QUDT = Namespace("http://qudt.org/schema/qudt/")
QUNIT = Namespace("http://qudt.org/vocab/unit/")
OA = Namespace("http://www.w3.org/ns/oa#")
XSD_NUMERIC = [XSD.float, XSD.decimal, XSD.integer, XSD.double]

SSL_VERIFY = os.getenv("SSL_VERIFY", "True").lower() in ("true", "1", "t")
if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()


def get_columns_from_schema(schema: URIRef, graph: Graph) -> OrderedDict:
    """_summary_

    Args:
        schema (URIRef): csvw.TableSchema to get columns objects from
        graph (Graph): Graph which includes the TableSchema

    Returns:
        OrderedDict: Dictionary with all Clumn informations attacked
    """
    column_collection_node = next(graph[schema : CSVW.column :], None)
    # collection must be queried in another way
    column_collection = Collection(graph, column_collection_node)
    columns = list(column_collection)
    return OrderedDict(
        [(column, {k: v for (k, v) in graph[column:]}) for column in columns]
    )


def parse_csv_from_url_to_list(
    csv_url,
    num_cols: int,
    delimiter: str = ",",
    skiprows: int = 0,
    num_header_rows: int = 2,
    encoding: str = "utf-8",
    authorization=None,
) -> List[List]:
    """Parses a csv file using the dialect given, to a list containing the content of every row as list.

    Args:
        csv_url (_type_): Url to the csv file to parse
        delimiter (str, optional): Delimiter for columns. Defaults to ','.
        skiprows (int, optional): Rows to Skip reading. Defaults to 0.
        num_header_rows (int, optional): Number of header rows with names of columns. Defaults to 2.
        encoding (str, optional): Encoding of the csv file. Defaults to 'utf-8'.

    Returns:
        List[List]: List of Lists with entrys for each row. Content of header rows are not included
    """
    file_data, file_name = open_file(csv_url, authorization=authorization)
    file_string = io.StringIO(file_data.decode(encoding))
    print(delimiter, num_header_rows + skiprows)
    table_data = pd.read_csv(
        file_string,
        header=None,
        sep=delimiter,
        usecols=range(num_cols),
        skiprows=num_header_rows + skiprows,
        encoding=encoding,
        skip_blank_lines=False,
        # on_bad_lines=test_bad_line,
        engine="python",
    )
    # remove data after blank line
    blank_df = table_data.loc[table_data.isnull().all(1)]
    if len(blank_df) > 0:
        first_blank_index = blank_df.index[0]
        table_data = table_data[:first_blank_index]
    # add a row index column
    line_list = table_data.to_numpy().tolist()
    line_list = [
        [
            index,
        ]
        + line
        for index, line in enumerate(line_list)
    ]
    return line_list


def open_file(uri: str, authorization=None) -> Tuple["filedata":str, "filename":str]:
    try:
        uri_parsed = urlparse(uri)
        # print(uri_parsed)

    except:
        raise HTTPException(
            status_code=400,
            detail=uri + " is not an uri - if local file add file:// as prefix",
        )
    else:
        filename = unquote(uri_parsed.path).rsplit("/download/upload")[0].split("/")[-1]
        if uri_parsed.scheme in ["https", "http"]:
            # r = urlopen(uri)
            s = requests.Session()
            s.verify = SSL_VERIFY
            s.headers.update({"Authorization": authorization})
            r = s.get(uri, allow_redirects=True, stream=True)

            r.raise_for_status()
            if r.status_code != 200:
                # logging.debug(r.content)
                raise HTTPException(
                    status_code=r.status_code, detail="cant get file at {}".format(uri)
                )
            filedata = r.content
            # charset=r.info().get_content_charset()
            # if not charset:
            #     charset='utf-8'
            # filedata = r.read().decode(charset)
        elif uri_parsed.scheme == "file":
            filedata = open(unquote(uri_parsed.path), "rb").read()
        else:
            raise HTTPException(
                status_code=400, detail="unknown scheme {}".format(uri_parsed.scheme)
            )
        return filedata, filename


def parse_graph(url: str, graph: Graph, format: str = "") -> Graph:
    """Parse a Graph from web url to rdflib graph object
    Args:
        url (AnyUrl): Url to an web ressource
        graph (Graph): Existing Rdflib Graph object to parse data to.
    Returns:
        Graph: Rdflib graph Object
    """
    logging.debug("parsing graph from {}".format(url))
    parsed_url = urlparse(url)
    META = Namespace(url + "/")
    # print(parsed_url)
    if not format:
        format = guess_format(parsed_url.path)
    if parsed_url.scheme in ["https", "http"]:
        graph.parse(urlopen(parsed_url.geturl()).read(), format=format)

    elif parsed_url.scheme == "file":
        print(parsed_url.path)
        graph.parse(parsed_url.path, format=format)
    graph.bind("meta", META)

    print(parsed_url)
    return graph


class CSVWtoRDF:
    """Class for Converting CSV data to RDF with help of CSVW Annotations"""

    def __init__(
        self,
        metadata_url: str,
        csv_url: str,
        api_url: None,
        metaformat: str = "json-ld",
        authorization=None,
    ) -> None:
        self.metadata_url = str(metadata_url)
        self.api_url = api_url
        # get metadata graph
        metadata_data, metadata_filename = open_file(
            self.metadata_url, authorization=authorization
        )
        self.metagraph = Graph()
        self.metagraph.parse(data=metadata_data, format=guess_format(metadata_filename))
        # self.metagraph=parse_graph(self.metadata_url,Graph(),format=metaformat)
        # self.metagraph.serialize('test.ttl',format='turtle')
        print(list(self.metagraph[: CSVW.url]))
        self.meta_root, url = list(self.metagraph[: CSVW.url])[0]
        # self.metagraph.serialize('metagraph.ttl')
        print("meta_root: " + self.meta_root)
        # print('csv_url: '+url)
        self.base_url = "{}/".format(quote(str(self.meta_root).rsplit("/", 1)[0]))
        parsed_url = urlparse(url)
        if parsed_url.scheme in ["https", "http", "file"]:
            self.csv_url = url
        else:
            if self.base_url.lower().endswith(url.lower() + "/"):
                self.csv_url = self.base_url[:-1]
            else:
                self.csv_url = self.base_url + url
        # replace if set in request
        if csv_url:
            self.csv_url = csv_url
        print(url, self.base_url, csv_url, self.csv_url)
        self.graph = Graph(base=self.csv_url + "/")
        print(self.metadata_url, self.csv_url)
        self.filename = self.csv_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        self.tables = {
            table_node: {} for file, table_node in self.metagraph[: CSVW.table :]
        }
        print("tables: {}".format(self.tables))
        self.table_data = list()
        if self.tables:
            for key, data in self.tables.items():
                dialect = next(self.metagraph[key : CSVW.dialect], None)
                data["dialect"] = {k: v.value for (k, v) in self.metagraph[dialect:]}
                # print(data['dialect'])
                data["schema"] = next(self.metagraph[key : CSVW.tableSchema :], None)
                data["columns"] = get_columns_from_schema(
                    data["schema"], self.metagraph
                )
                # print(data['columns'])
                # get table form csv_url
                if data["schema"]:
                    data["about_url"] = next(
                        self.metagraph[data["schema"] : CSVW.aboutUrl], None
                    )
                    # print(data['dialect'])
                    print(
                        "skipRows: {} headerRowCount: {}".format(
                            data["dialect"][CSVW.skipRows],
                            data["dialect"][CSVW.headerRowCount],
                        )
                    )
                    data["lines"] = parse_csv_from_url_to_list(
                        self.csv_url,
                        delimiter=data["dialect"][CSVW.delimiter],
                        skiprows=data["dialect"][CSVW.skipRows],
                        # always on column less, index is created after reading
                        num_cols=len(data["columns"].keys()) - 1,
                        num_header_rows=data["dialect"][CSVW.headerRowCount],
                        encoding=data["dialect"][CSVW.encoding],
                        authorization=authorization,
                    )

    def add_table_data(self, g: Graph) -> Graph:
        """_summary_

        Args:
            g (Graph): Grapg to add the table data tripells to

        Returns:
            Graph: Input Graph return with triples of table added
        """
        for table, data in self.tables.items():
            print("table: {}, about_url: {}".format(table, data["about_url"]))
            # g.add((table_group,CSVW.table, table))
            g.add((table, RDF.type, CSVW.Table))
            if data["about_url"]:
                row_uri = data["about_url"]
            else:
                row_uri = "table-{TABLE}-gid-{GID}".format(table)

            columns = list(data["columns"].items())
            for index, row in enumerate(data["lines"]):
                # print(index, row)
                row_node = BNode()
                values_node = URIRef(row_uri.format(GID=index))
                g.add((table, CSVW.row, row_node))
                g.add((row_node, RDF.type, CSVW.Row))
                g.add((row_node, CSVW.describes, values_node))
                row_num = (
                    index
                    + data["dialect"][CSVW.skipRows]
                    + data["dialect"][CSVW.headerRowCount]
                )
                g.add(
                    (
                        row_node,
                        CSVW.url,
                        URIRef("{}/row={}".format(self.csv_url, row_num)),
                    )
                )
                for cell_index, cell in enumerate(row):
                    # print(self.columns[cell_index])
                    column_data = columns[cell_index][1]
                    if column_data[CSVW.name] == Literal("GID"):
                        continue
                    format = column_data.get(CSVW.format, XSD.string)
                    unit = column_data.get(QUDT.unit, None)
                    if format == XSD.double and isinstance(cell, str):
                        cell = cell.replace(".", "")
                        cell = cell[::-1].replace(",", ".", 1)[::-1]

                    if format in XSD_NUMERIC:
                        value_node = BNode()
                        g.add((value_node, RDF.type, QUDT.QuantityValue))
                        g.add((value_node, QUDT.value, Literal(cell)))
                        if unit:
                            g.add((value_node, QUDT.unit, unit))
                    elif format == XSD.anyURI:
                        # see if its a list of uris
                        if len(cell.split(" ")) >= 1:
                            value_node = BNode()
                            uris = list(map(URIRef, cell.split(" ")))
                            Collection(g, value_node, uris)
                        else:
                            value_node = URIRef(cell)
                    else:
                        value_node = BNode()
                        body_node = BNode()
                        g.add((value_node, RDF.type, OA.Annotation))
                        g.add((value_node, OA.hasBody, body_node))
                        g.add((body_node, RDF.type, OA.TextualBody))
                        g.add((body_node, DC.format, Literal("text/plain")))
                        g.add((body_node, RDF.value, Literal(cell, datatype=format)))

                    # if isinstance(column,URIRef) and str(self.meta_root)!='file:///src/': #has proper uri
                    #     g.add((value_node, column, Literal(cell)))

                    if CSVW.aboutUrl in column_data.keys():
                        aboutUrl = column_data[CSVW.aboutUrl]
                        print("about url:{}".format(aboutUrl))
                        g.add(
                            (
                                values_node,
                                URIRef(aboutUrl.format(GID=index)),
                                value_node,
                            )
                        )
                    else:
                        name = column_data[CSVW.name]
                        g.add(
                            (
                                values_node,
                                URIRef("{}-{}".format(table, name)),
                                value_node,
                            )
                        )
        return g
        # self.atdm, self.metadata =converter.convert_to_atdm('standard')

    def convert(self, format: str = "turtle") -> str:
        """_summary_

        Args:
            format (str, optional): serialization format to output the graph

        Returns:
            str: serialize graph as string
        """
        if format in ["turtle", "longturtle"]:
            self.filename += ".ttl"
        elif format == "json-ld":
            self.filename += ".json"
        else:
            self.filename += "." + format
        self.graph = self.graph + self.metagraph
        # print(list(graph.namespaces()))

        self.graph = self.add_table_data(self.graph)
        if self.api_url:
            self.graph = csvwtordf_prov(
                self.graph, self.api_url, self.csv_url, self.metadata_url
            )
        print(self.filename, format)
        return self.graph.serialize(format=format)


import settings

setting = settings.Setting()


def csvwtordf_prov(graph: Graph, api_url: str, csv_url: str, metadata_url: str) -> dict:
    """_summary_

    Args:
        graph (Graph): Graph to add prov information to
        api_url (str): the api url
        csv_url (str): the url to the csv file that was annotated
        metadata_url (str): the url to the metadata file that has annotation for a csv

    Returns:
        Graph: Input Graph with prov metadata of the api call
    """
    graph.bind("prov", PROV)
    tables = list(graph[: RDF.type : CSVW.Table])
    print(tables)
    for table in tables:
        api_node = URIRef(api_url)
        graph.add((table, PROV.wasGeneratedBy, api_node))
        graph.add((api_node, RDF.type, PROV.Activity))
        software_node = URIRef(
            "https://github.com/Mat-O-Lab/CSVToCSVW/releases/tag/" + setting.version
        )
        graph.add((api_node, PROV.wasAssociatedWith, software_node))
        graph.add((software_node, RDF.type, PROV.SoftwareAgent))
        graph.add(
            (software_node, RDFS.label, Literal(setting.app_name + setting.version))
        )
        graph.add((software_node, PROV.hadPrimarySource, URIRef(setting.source)))
        graph.add(
            (
                table,
                PROV.generatedAtTime,
                Literal(str(datetime.now().isoformat()), datatype=XSD.dateTime),
            )
        )
        csv_usage = URIRef(csv_url)
        graph.add((csv_usage, RDF.type, PROV.Usage))
        graph.add((csv_usage, PROV.hadRole, CSVW.csvEncodedTabularData))
        graph.add((table, PROV.qualifiedUsage, csv_usage))
        meta_usage = URIRef(metadata_url)
        graph.add((meta_usage, RDF.type, PROV.Usage))
        graph.add((meta_usage, PROV.hadRole, CSVW.tabularMetadata))
        graph.add((table, PROV.qualifiedUsage, meta_usage))
    return graph
