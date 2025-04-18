# app.py

from flask import Flask, render_template, request, jsonify
import timetable_extractor  # Import your extraction module
import traceback # Import traceback

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    """
    Renders the main page with the section selection form.
    """
    return render_template('index.html')

@app.route('/timetable', methods=['POST'])
def get_timetable():
    """
    Extracts timetable data for a given section from the PDF and returns it as JSON.
    Handles errors and returns appropriate responses.
    """
    try:
        pdf_path = 'CSE 1st Year Section Wise.pdf'  #  Make sure this is correct
        target_section = request.form['section']  # Get section from form
        section_name, timetable_data = timetable_extractor.extract_timetable_data(pdf_path, target_section)
        
        if not timetable_data:
            return jsonify({'error': 'No timetable data found for this section.', 'section': target_section}), 404
        
        return jsonify({'section': section_name, 'timetable': timetable_data}), 200 # Return JSON data
    
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        print(traceback.format_exc())  # Print the traceback to the console
        return jsonify({'error': error_message, 'traceback': traceback.format_exc()}), 500 # Return JSON error

if __name__ == '__main__':
    app.run(debug=True)
