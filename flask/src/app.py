from src.csv_to_csvw.annotator import CSV_Annotator

import os
from flask import Flask, flash, request, redirect, url_for, Response, render_template, send_file
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'csv', 'rdf', 'txt', 'tra'}

done = False
result = None

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    print("uploaded file")
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        print(file.filename == '')
        if file.filename == '':
            print("No selected file")
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):

            print("file was allowed")
            filename = secure_filename(file.filename)

            separator = request.form["separator"]
            encoding = request.form["encoding"]

            tmp = CSV_Annotator(encoding=encoding, separator=separator, file=file)

            # may return an error. in this case the return value result holds the error info
            meta_file_name, result = tmp.process()


            if meta_file_name == "error":
                flash(result)
                return render_template("index.html")

            return Response(result, mimetype='text/json', headers={"Content-Disposition" : "attachment; filename="+meta_file_name})

    return render_template("index.html")

if __name__ == "__main__":
    app.secret_key =  b'O$2\xe1BI\x16\x94\x95\x89&\xb8\xc4\x9f\x1d\xd4\xc6\xc7m9\x9d\xc4\xeb^'
    app.run(debug=False)