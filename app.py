from flask import Flask,request,render_template,send_file
import pdfplumber
import os
import docx
import csv
from werkzeug.utils import secure_filename
import google.generativeai as genai
from fpdf import FPDF


#set your API key
os.environ["GOOGLE_API_KEY"] ="AIzaSyBuKJOAYX_LvTxBoz32kgz-EoqswEKuypU"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model=genai.GenerativeModel("models/gemini-1.5-pro")

app=Flask(__name__)
app.config['UPLOAD_FOLDER']='uploads/'
app.config['RESULTS_FOLDER']='results/'
app.config['ALLOWED_EXTENSIONS']={'pdf','txt','docx'}
#custom functions
def allowed_file(filename):
   return '.' in filename and filename.rsplit('.',1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
 
def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
      with pdfplumber.open(file_path) as pdf:
         text = ''.join([page.extract_text() for page in pdf.pages])
        #  print("Extracted text:", text)  # Debugging
      return text
    elif ext == 'docx':
        doc=docx.Document(file_path)
        text = ''.join([para.text for para in doc.paragraphs])
        return text
    elif ext == 'txt':
       with open(file_path,'r') as file :
         return file.read()
    return None
   
def Question_mcqs_generator(input_text, num_questions):
    prompt = f"""
    You are an AI assistant helping the user generate multiple-choice questions (MCQs) based on the following text:
    '{input_text}'
    Please generate {num_questions} MCQs from the text. Each question should have:
    - A clear question
    - Four answer options (labeled A, B, C, D)
    - The correct answer clearly indicated
    Format:
    ## MCQ
    Question: [question]
    A) [option A]
    B) [option B]
    C) [option C]
    D) [option D]
    Correct Answer: [correct option]
    """

    response = model.generate_content(prompt)
    print("API Response:", response)  # Log response for debugging

    if not response:
        print("Received empty response.")
        return "Failed to generate MCQs."

    # Extract MCQs if they're in a structured format
    # Assuming response is a text block with multiple MCQs formatted similarly to the prompt
    mcqs = response.split('## MCQ')
    mcqs = [mcq.strip() for mcq in mcqs if mcq.strip()]  # Clean and remove empty blocks

    if len(mcqs) == 0:
        print("No MCQs were generated.")
        return "No MCQs generated from the provided text."

    # Return formatted MCQs or render them in the template
    return '\n\n'.join(mcqs)

def save_mcqs_to_file(mcqs, filename):
    results_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    with open(results_path, 'w') as f:
        f.write(mcqs)
    return results_path
#routes(end points)

@app.route("/")
def index():
    return render_template('index.html')
@app.route("/generate", methods=["POST"])
def generate_mcqs():
    if 'file' not in request.files:
       return "No file part"
    file=request.files['file']
    if file and allowed_file(file.filename):
       filename=secure_filename(file.filename)
       file_path=os.path.join(app.config['UPLOAD_FOLDER'],filename)
       file.save(file_path)

       #pdf,txt,docx
       text=extract_text_from_file(file_path)
    #    print(text)
       if text:
          num_questions=request.form['num_questions']
          mcqs=Question_mcqs_generator(text,num_questions)
          # Save the generated MCQs to a file
          txt_filename = f"generated_mcqs_{filename.rsplit('.', 1)[0]}.txt"
          pdf_filename = f"generated_mcqs_{filename.rsplit('.', 1)[0]}.pdf"
          save_mcqs_to_file(mcqs, txt_filename)
          create_pdf(mcqs, pdf_filename)

          # Display and allow downloading
          return render_template('results.html', mcqs=mcqs, txt_filename=txt_filename, pdf_filename=pdf_filename)
    return "Invalid file format"

def create_pdf(mcqs, filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for mcq in mcqs.split("## MCQ"):
        if mcq.strip():
            pdf.multi_cell(0, 10, mcq.strip())
            pdf.ln(5)  # Add a line break

    pdf_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
    pdf.output(pdf_path)
    return pdf_path

@app.route('/download/<filenmae>')
def download_file(filename):
   file_path=os.path.join(app.config['RESULTS_FOLDER'])
   return send_file(file_path,as_attachment=True)
#python main
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
      os.makedirs(app.config['UPLOAD_FOLDER'])
    if not os.path.exists(app.config['RESULTS_FOLDER']):
      os.makedirs(app.config['RESULTS_FOLDER'])
    app.run(debug=True)
