# CSVToCSVW
[![Publish Docker image](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/PublishContainer.yml/badge.svg)](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/PublishContainer.yml)
[![TestExamples](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/TestExamples.yml/badge.svg?branch=main)](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/TestExamples.yml)

Generates JSON-LD for various types of CSVs, it adopts the Vocabulary provided by w3c at [CSVW](https://www.w3.org/ns/csvw) to describe structure and information within. Also uses [QUDT units ontology](https://github.com/qudt/qudt-public-repo/tree/main/vocab/unit) to lookup and describe units. 
Can segment complex csv files with multiple tables and annotation without further input. Has also an option to output complete serialized content of the csv in csvw standard output format through rdf api endpoint.
# how to use

## create a .env file with
```bash
APP_PORT=<80>
ADMIN_MAIL=<email_of_admin>
```

## docker
Just pull the docker container from the github container registry
```bash
docker pull ghcr.io/mat-o-lab/csvtocsvw:latest
```

## docker-compose
Clone the repo with 
```bash
git clone https://github.com/Mat-O-Lab/CSVToCSVW
```
cd into the cloned folder
```bash
cd CSVToCSVW
```
Build and start the container.
```bash
docker-compose up
```

A simple UI can be found at at the index page '/'
The API documentation at 'api/docs'

## jupyter notebook
1. Open the notebook in or any other jupyter instance.[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Mat-O-Lab/CSVToCSVW/blob/main/csv_parser.ipynb)
2. Run the first cell of the notebook. It will install the necesary python packages and definitions.
3. Run the second cell
4. Upload a csv file or paste in a url pointing at one in the provided widgets.
5. Click the process button, it will try to determine encoding and column seperator automatically. If that fails, choose appropiate values from the drop downs in the widgets and press the process button again. 
6. If successful the json-ld created will be printed to the cell as output. Click the download button to download the code in the proper filename acoording to https://www.w3.org/ns/csvw.
7. Place the file in the same folder then the csv it describes.
