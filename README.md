# CSVToCSVW
Generates JSON-LD for various types CSVs, it adopts the Vocabulary provided by w3c at https://www.w3.org/ns/csvw to describe structure and information.

# how to use
1. Open the notebook in [google colab](https://colab.research.google.com) or any other jupyter instance.
2. Run the first cell of the notebook. It will install the necesary python packages and definitions.
3. Run the second cell
4. Upload a csv file or paste in a url pointing at one in the provided widgets.
5. Click the process button, it will try to determine encoding and column seperator automatically. If that fails, choose appropiate values from the drop downs in the widgets and press the process button again. 
6. If successful the json-ld created will be printed to the cell as output. Click the download button to download the code in the proper filename acoording to https://www.w3.org/ns/csvw.
7. Place the file in the same folder then the csv it describes.

# Docker
Start the container with 'docker-compose up'