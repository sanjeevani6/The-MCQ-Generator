from flask import Flask, request, render_template, redirect, url_for, send_file
import pdfplumber
import os
import docx
import threading
import json
from werkzeug.utils import secure_filename
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
import re
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Initialize Flask App
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULTS_FOLDER'] = 'results/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt', 'docx'}

MAX_TEXT_LENGTH = 1000
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# State management
generated_results = {}
processing_status = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    text = ""

    try:
        if ext == 'pdf':
            with pdfplumber.open(file_path) as pdf:
                text = ''.join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif ext == 'docx':
            doc = docx.Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
        elif ext == 'txt':
            with open(file_path, 'r', encoding="utf-8") as file:
                text = file.read()
        
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "..."
        return text
    except Exception as e:
        print(f" File processing error: {str(e)}")
        return None

def Question_mcqs_generator(input_text, num_questions,difficulty):
    try:
        llm = OllamaLLM(model="llama3.2")
        prompt_template = PromptTemplate(
            input_variables=["text", "num_questions","difficulty"],
            template="""You are an expert in educational content creation.
Generate {num_questions} multiple-choice questions (MCQs) from the following text:
"{text}"

The difficulty level should be: {difficulty}.

Each MCQ should have:
- A clear question
- Four answer options (A, B, C, D)
- The correct answer clearly indicated.

Output the result in valid JSON format like this:
[
    {{
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin", "Madrid"],
        "correct_answer": "Paris"
    }}
]
"""
        )

        chain = prompt_template | llm  
        response = chain.invoke({"text": input_text, "num_questions": num_questions,"difficulty": difficulty})

        json_match = re.search(r"\[\s*\{.*?\}\s*\]", response, re.DOTALL)
        if not json_match:
            print(" No valid JSON found in response!")
            return None

        json_text = json_match.group(0)
        json_text = re.sub(r'[\x00-\x1F\x7F]', '', json_text)  # Clean non-printable chars
        
        return json.loads(json_text)
    except Exception as e:
        print(f" Generation Error: {str(e)}")
        return None

def save_mcqs_to_txt(filename, mcqs):
    txt_file_path = os.path.join(app.config['RESULTS_FOLDER'], f"{filename}.txt")
    with open(txt_file_path, "w", encoding="utf-8") as file:
        for mcq in mcqs:
            file.write(f"Q: {mcq['question']}\n")
            file.write(f"A) {mcq['options'][0]}\n")
            file.write(f"B) {mcq['options'][1]}\n")
            file.write(f"C) {mcq['options'][2]}\n")
            file.write(f"D) {mcq['options'][3]}\n")
            file.write(f"Correct Answer: {mcq['correct_answer']}\n\n")
    return txt_file_path

def save_mcqs_to_pdf(filename, mcqs):
    pdf_file_path = os.path.join(app.config['RESULTS_FOLDER'], f"{filename}.pdf")
    c = canvas.Canvas(pdf_file_path, pagesize=letter)
    y = 750

    c.setFont("Helvetica", 12)
    for mcq in mcqs:
        c.drawString(50, y, f"Q: {mcq['question']}")
        y -= 20
        c.drawString(70, y, f"A) {mcq['options'][0]}")
        y -= 20
        c.drawString(70, y, f"B) {mcq['options'][1]}")
        y -= 20
        c.drawString(70, y, f"C) {mcq['options'][2]}")
        y -= 20
        c.drawString(70, y, f"D) {mcq['options'][3]}")
        y -= 20
        c.drawString(50, y, f"Correct Answer: {mcq['correct_answer']}")
        y -= 40
        if y < 100:
            c.showPage()
            y = 750

    c.save()
    return pdf_file_path

def async_mcq_generation(text, num_questions, filename,difficulty):
    try:
        processing_status[filename] = "processing"
        
        # Generate MCQs from provided text input
        mcqs = Question_mcqs_generator(text, num_questions,difficulty)

        if mcqs:
            txt_path = save_mcqs_to_txt(filename, mcqs)
            pdf_path = save_mcqs_to_pdf(filename, mcqs)

            generated_results[filename] = {
                "mcqs": mcqs,
                "txt_filename": txt_path,
                "pdf_filename": pdf_path
            }
            processing_status[filename] = "complete"
        else:
            processing_status[filename] = "error: Failed to generate valid MCQs"
            
    except Exception as e:
        processing_status[filename] = f"error: {str(e)}"

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/generate", methods=["POST"])
def generate_mcqs():
        # Get difficulty input from form, default to 'medium' if not provided
    difficulty = request.form.get('difficulty', 'medium')
    # Check for direct text input first
    text_input = request.form.get('text', '').strip()
    
    if text_input:  # If there is text input provided by the user
        text = text_input[:MAX_TEXT_LENGTH] + "..." if len(text_input) > MAX_TEXT_LENGTH else text_input
        base_name = "text_input"  # Assign a default name for text input
    else:  # If no direct text is provided, then check for file upload
        if 'file' not in request.files or request.files['file'].filename == '':
            return "No input provided! Please enter text or upload a file.", 400
            
        file = request.files['file']
        
        if not allowed_file(file.filename):
            return "Unsupported file format. Please upload a PDF, DOCX, or TXT file.", 400

        filename = secure_filename(file.filename)
        
        # Save uploaded file temporarily and extract text from it.
        base_name = filename.rsplit('.', 1)[0]  # Assign base_name here
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save uploaded file to server.
        file.save(file_path)

        # Extract text from uploaded document.
        text = extract_text_from_file(file_path)

        if not text: 
            return "Failed to extract text from input.", 400 

    num_questions = int(request.form.get('num_questions', 5))

    thread = threading.Thread(target=async_mcq_generation, args=(text, num_questions, base_name,difficulty))
    thread.start()

    return redirect(url_for('show_results', filename=base_name))


@app.route("/results/<filename>")
def show_results(filename):
    status = processing_status.get(filename, "not_found")

    if status == "complete":
        return render_template("result.html", mcqs=generated_results[filename]["mcqs"], filename=filename)
    elif status == "processing":
        return render_template("processing.html")
    elif status.startswith("error:"):
        return f"<h2>Error</h2><p>{status.split('error:')[1].strip()}</p>", 500
   
    return "Results not found.", 404

@app.route("/download/txt/<filename>")
def download_txt(filename):
    return send_file(generated_results[filename]["txt_filename"], as_attachment=True)

@app.route("/download/pdf/<filename>")
def download_pdf(filename):
    return send_file(generated_results[filename]["pdf_filename"], as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=10000,debug=True)
