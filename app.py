from annotator import CSV_Annotator

import zipfile
from io import BytesIO
from flask import Flask, flash, request, redirect, url_for, Response, render_template, send_file, stream_with_context
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "tmp"
ALLOWED_EXTENSIONS = {'csv', 'rdf', 'txt', 'tra'}

done = False
result = None
debug = True

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
        if 'files' not in request.files:
            flash('No file part')
            return redirect(request.url)


        files = request.files.getlist("files")

        separator = request.form["separator"]
        encoding = request.form["encoding"]

        # create annotator object for reading files
        annotator = CSV_Annotator(encoding=encoding, separator=separator)

        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for file in files:

                if file.filename == '':
                    print("No selected file")
                    flash('No selected file')
                    continue

                if file and allowed_file(file.filename):

                    filename = secure_filename(file.filename)
                    file.filename = filename
                    meta_file_name, result = annotator.process(file)
                    zf.writestr(zinfo_or_arcname=meta_file_name, data=result)

        memory_file.seek(0)
        return send_file(memory_file, attachment_filename='result.zip', as_attachment=True)

    return render_template("index.html")

if __name__ == "__main__":
    app.secret_key =  b'O$2\xe1BI\x16\x94\x95\x89&\xb8\xc4\x9f\x1d\xd4\xc6\xc7m9\x9d\xc4\xeb^'
    app.run(debug=False)