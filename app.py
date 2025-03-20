from flask import Flask, request, render_template, send_file, redirect, url_for
import pdfplumber
import os
import docx
import threading
import json  # Added for JSON parsing
from werkzeug.utils import secure_filename
from fpdf import FPDF
from langchain_ollama import OllamaLLM  # type: ignore
from langchain_core.prompts import PromptTemplate
import re  # Import regex to extract JSON

# Initialize Flask App
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULTS_FOLDER'] = 'results/'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt', 'docx'}

MAX_TEXT_LENGTH = 1000  # Limit input text length for processing

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# Store generated results
generated_results = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Extract text from different file formats
def extract_text_from_file(file_path):
    ext = file_path.rsplit('.', 1)[1].lower()
    print(f"📂 Processing file: {file_path} (Type: {ext})")
    text = ""

    if ext == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            text = ''.join([page.extract_text() for page in pdf.pages if page.extract_text()])
    elif ext == 'docx':
        doc = docx.Document(file_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
    elif ext == 'txt':
        with open(file_path, 'r', encoding="utf-8") as file:
            text = file.read()

    print(f"✅ Extracted {len(text)} characters from {ext.upper()} file.")
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "..."
        print(f"⚠️ Text truncated to {MAX_TEXT_LENGTH} characters to improve performance.")
    return text

# Generate MCQs using Llama 3
def Question_mcqs_generator(input_text, num_questions):
    print("🚀 Calling Llama 3 for MCQ generation...")
    print(f"📜 Text Length: {len(input_text)} characters | 🔢 MCQs Requested: {num_questions}")

    llm = OllamaLLM(model="llama3")

    prompt_template = PromptTemplate(
        input_variables=["text", "num_questions"],
        template="""You are an expert in educational content creation.
        Generate {num_questions} multiple-choice questions (MCQs) from the following text:
        "{text}"
        
        Each MCQ should have:
        - A clear question
        - Four answer options (A, B, C, D)
        - The correct answer clearly indicated.
        
        Output the result in **valid JSON format**:
        ```json
        [
            {{
                "question": "MCQ Question 1",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": "Option A"
            }},
            {{
                "question": "MCQ Question 2",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": "Option B"
            }}
        ]
        ```
        """
    )

    chain = prompt_template | llm  
    response = chain.invoke({"text": input_text, "num_questions": num_questions})
    print(f"🟢 DEBUG: Llama 3 Raw Response: {response}")


      # Use regex to extract JSON part
    json_match = re.search(r"\[\s*\{.*?\}\s*\]", response, re.DOTALL)

    if json_match:
        json_text = json_match.group(0)  # Extract only the JSON part
        try:
            mcq_list = json.loads(json_text)  # Parse JSON
            print("✅ MCQs parsed successfully!")
            return mcq_list
        except json.JSONDecodeError:
            print("❌ ERROR: Failed to parse extracted JSON!")
    else:
        print("❌ ERROR: No valid JSON found in response!")

    return []  # Return empty list if parsing fails


# Background function for MCQ generation
def async_mcq_generation(text, num_questions, filename):
    print("🛠️ Running MCQ generation in the background...")
    mcqs = Question_mcqs_generator(text, num_questions)

    if not mcqs:
        return

    txt_filename = f"generated_mcqs_{filename}.txt"
    pdf_filename = f"generated_mcqs_{filename}.pdf"

    generated_results[filename] = {
        "mcqs": mcqs,
        "txt_filename": txt_filename,
        "pdf_filename": pdf_filename
    }

    print(f"✅ MCQ generation completed in the background for {filename}")

# Flask Routes
@app.route("/")
def index():
    return render_template('index.html')

@app.route("/generate", methods=["POST"])
def generate_mcqs():
    print("📤 Receiving file upload...")

    if 'file' not in request.files:
        print("❌ ERROR: No file uploaded.")
        return "No file uploaded."

    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        print(f"✅ File saved: {file_path}")

        text = extract_text_from_file(file_path)
        if text:
            num_questions = int(request.form.get('num_questions', 5))
            thread = threading.Thread(target=async_mcq_generation, args=(text, num_questions, filename.rsplit('.', 1)[0]))
            thread.start()
            return redirect(url_for('show_results', filename=filename.rsplit('.', 1)[0]))

    print("❌ ERROR: Invalid file format.")
    return "Invalid file format."

@app.route("/results/<filename>")
def show_results(filename):
    if filename in generated_results:
        return render_template(
            "result.html",
            mcqs=generated_results[filename]["mcqs"],
            txt_filename=generated_results[filename]["txt_filename"],
            pdf_filename=generated_results[filename]["pdf_filename"]
        )
    return "Results not found."

if __name__ == '__main__':
    print("🚀 Starting Flask App...")
    app.run(debug=True)



