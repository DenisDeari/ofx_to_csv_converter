import logging
import os
from flask import Flask, render_template, request, Response
import csv
from io import StringIO, BytesIO
from ofxparse import OfxParser
import zipfile

app = Flask(__name__)

# Configure logging to file with timestamp and log level.
logging.basicConfig(
    level=logging.INFO,
    filename='app.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)

ALLOWED_EXTENSIONS = {'.ofx'}

def allowed_file(filename):
    """Check if the file has an allowed extension."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        files = request.files.getlist('ofx_file')
        if not files or len(files) == 0:
            logging.error("No file provided in the request.")
            return render_template("error.html", error_message="No file provided."), 400

        output_type = request.form.get("output_type", "single")  # "single" or "multiple"
        successful_files = 0
        error_messages = []

        if output_type == "single":
            # Build a single CSV combining all transactions
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Date", "Amount", "Type", "Name", "Memo"])
            for file in files:
                if file.filename == '':
                    logging.warning("Encountered a file with an empty filename; skipping.")
                    continue
                if not allowed_file(file.filename):
                    msg = f"File {file.filename} is not a valid OFX file."
                    logging.error(msg)
                    error_messages.append(msg)
                    continue
                try:
                    ofx = OfxParser.parse(file)
                    file_processed = False
                    for account in ofx.accounts:
                        for txn in account.statement.transactions:
                            try:
                                date_str = txn.date.strftime("%Y-%m-%d") if txn.date else ""
                            except Exception as e:
                                date_str = ""
                                logging.warning(f"Error formatting date in file {file.filename}: {e}")
                            writer.writerow([
                                date_str,
                                txn.amount,
                                txn.type,
                                txn.payee,
                                txn.memo
                            ])
                            file_processed = True
                    if file_processed:
                        successful_files += 1
                        logging.info(f"Processed file {file.filename} successfully.")
                    else:
                        msg = f"No transactions found in file {file.filename}."
                        logging.warning(msg)
                        error_messages.append(msg)
                except Exception as e:
                    msg = f"Error processing file {file.filename}: {e}"
                    logging.exception(msg)
                    error_messages.append(msg)
            if successful_files == 0:
                final_error = "None of the provided files were processed successfully. " + " | ".join(error_messages)
                logging.error(final_error)
                return render_template("error.html", error_message=final_error), 500

            csv_data = output.getvalue()
            response = Response(
                csv_data,
                mimetype="text/csv",
                headers={"Content-disposition": "attachment; filename=output.csv"}
            )
            # Optionally include warnings in the header.
            if error_messages:
                response.headers["X-Warnings"] = " | ".join(error_messages)
            logging.info("CSV conversion (single file) completed successfully.")
            return response

        elif output_type == "multiple":
            # Build a ZIP archive containing one CSV per OFX file.
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file in files:
                    if file.filename == '':
                        logging.warning("Encountered a file with an empty filename; skipping.")
                        continue
                    if not allowed_file(file.filename):
                        msg = f"File {file.filename} is not a valid OFX file."
                        logging.error(msg)
                        error_messages.append(msg)
                        continue
                    try:
                        ofx = OfxParser.parse(file)
                        file_processed = False
                        csv_output = StringIO()
                        writer = csv.writer(csv_output)
                        writer.writerow(["Date", "Amount", "Type", "Name", "Memo"])
                        for account in ofx.accounts:
                            for txn in account.statement.transactions:
                                try:
                                    date_str = txn.date.strftime("%Y-%m-%d") if txn.date else ""
                                except Exception as e:
                                    date_str = ""
                                    logging.warning(f"Error formatting date in file {file.filename}: {e}")
                                writer.writerow([
                                    date_str,
                                    txn.amount,
                                    txn.type,
                                    txn.payee,
                                    txn.memo
                                ])
                                file_processed = True
                        if file_processed:
                            successful_files += 1
                            logging.info(f"Processed file {file.filename} successfully.")
                            base_name = os.path.splitext(file.filename)[0]
                            csv_filename = f"{base_name}.csv"
                            zip_file.writestr(csv_filename, csv_output.getvalue())
                        else:
                            msg = f"No transactions found in file {file.filename}."
                            logging.warning(msg)
                            error_messages.append(msg)
                    except Exception as e:
                        msg = f"Error processing file {file.filename}: {e}"
                        logging.exception(msg)
                        error_messages.append(msg)
            if successful_files == 0:
                final_error = "None of the provided files were processed successfully. " + " | ".join(error_messages)
                logging.error(final_error)
                return render_template("error.html", error_message=final_error), 500

            zip_buffer.seek(0)
            response = Response(
                zip_buffer.getvalue(),
                mimetype="application/zip",
                headers={"Content-disposition": "attachment; filename=output.zip"}
            )
            if error_messages:
                response.headers["X-Warnings"] = " | ".join(error_messages)
            logging.info("CSV conversion (multiple files in zip) completed successfully.")
            return response

        else:
            logging.error("Invalid output type selected.")
            return render_template("error.html", error_message="Invalid output type selected."), 400

    return render_template('index.html')

# Custom error handlers for additional reporting
@app.errorhandler(404)
def not_found_error(error):
    return render_template("error.html", error_message="Page not found."), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", error_message="An internal error occurred."), 500

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)