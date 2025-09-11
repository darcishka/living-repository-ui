import os
import uuid
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
import pyodbc
import bcrypt
import pytesseract
from PIL import Image
import fitz
from docx import Document as DocxDocument
import google.generativeai as genai
import re

# ------------------ App Setup -----------------------
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.secret_key = "super-secret-key"  # change this in production!

# Configure Google Gemini API
genai.configure(api_key="AIzaSyAYH1bmWz4hI1s2rgFXvAR5ygtOmoXf4Cs")
model = genai.GenerativeModel("Gemini 2.5-Flash-Lite")

# ------------------ Database Helper -----------------
def get_db():
    """Return a connection to Azure SQL using ODBC Driver 18 and TLS 1.2."""
    server = "tcp:kit300.database.windows.net,1433"
    database = "living_repository"
    username = "living_repository@kit300"
    password = "{4pplec4r7b$77ery}"

    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    conn = pyodbc.connect(conn_str)
    return conn

def dict_cursor(cursor):
    """Return rows as dictionaries."""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_project_title(project_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT title FROM Project WHERE project_id=?", (project_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else "Unknown Project"

# ------------------ Document & Tag Functions ----------------
def generate_tags(text):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = f"Extract 5-10 concise topic tags for the following document, respond with the tags only, separated by commas:\n\n{text[:3000]}"
        response = model.generate_content(prompt)
        tags = response.text.strip().split(",")
        return [t.strip() for t in tags if t.strip()]
    except Exception as e:
        print("Tagging error:", e)
        return []

def get_or_create_tag(cur, label, category="auto"):
    cur.execute("SELECT tag_id FROM Tag WHERE label = ?", (label,))
    row = cur.fetchone()
    if row:
        return row[0]
    new_id = str(uuid.uuid4())
    cur.execute("INSERT INTO Tag (tag_id, label, category) VALUES (?, ?, ?)", (new_id, label, category))
    return new_id

def extract_word_text(path):
    text = ""
    doc = DocxDocument(path)
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def extract_pdf_text(path):
    text = ""
    pdf = fitz.open(path)
    for page in pdf:
        text += page.get_text()
    pdf.close()
    return text

# ------------------ Routes -----------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html", current_year=datetime.datetime.now().year)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ------------------ Authentication -----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    
    email = request.form["email"]
    password = request.form["password"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, password_hash FROM [User] WHERE email = ?", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return "Invalid email or password"

    user_id, name, hashed = row
    if bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")):
        session["user_id"] = user_id
        session["name"] = name
        return redirect(url_for("dashboard"))
    else:
        return "Invalid email or password"

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    name = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    if not name or not email or not password:
        return "Missing field!"

    user_id = str(uuid.uuid4())
    role = "user"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM [User] WHERE email=?", (email,))
    exists = cur.fetchone()[0]
    if exists > 0:
        return "Email already taken"

    cur.execute("INSERT INTO [User] (user_id, name, email, role, password_hash) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, email, role, hashed.decode("utf-8")))
    conn.commit()
    cur.close()
    conn.close()

    return "Account created successfully! <a href='/login'>Login here</a>"

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", name=session["name"])

# ------------------ Project Routes -----------------
@app.route("/projects")
def projects():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.project_id, p.title, p.description, up.permission
        FROM Project p
        JOIN User_Project up ON p.project_id = up.project_id
        WHERE up.user_id = ?
    """, (user_id,))
    projects = dict_cursor(cur)
    cur.close()
    conn.close()
    return render_template("projects.html", projects=projects)

@app.route("/create_project", methods=["GET", "POST"])
def create_project():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("create_project.html")

    title = request.form["title"]
    description = request.form["description"]
    project_id = str(uuid.uuid4())

    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO Project (project_id, title, description, creation_date) VALUES (?, ?, ?, ?)",
                (project_id, title, description, datetime.datetime.now()))
    cur.execute("INSERT INTO User_Project (user_id, project_id, permission, join_date) VALUES (?, ?, ?, ?)",
                (session["user_id"], project_id, "admin", datetime.datetime.now()))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("projects"))

@app.route("/project/<project_id>")
def project_detail(project_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Fetch project info
    cur.execute("SELECT title, description FROM Project WHERE project_id=?", (project_id,))
    project = cur.fetchone()
    if not project:
        cur.close()
        conn.close()
        return "Project not found"

    columns = [column[0] for column in cur.description]
    project = dict(zip(columns, project))

    # Fetch documents
    cur.execute("""
        SELECT d.doc_id, d.title
        FROM Document d
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        WHERE pd.project_id=?
    """, (project_id,))
    documents = dict_cursor(cur)

    cur.close()
    conn.close()

    return render_template("project_detail.html",
                           project_id=project_id,
                           project_title=project["title"],
                           project_description=project["description"],
                           documents=documents,
                           current_year=datetime.datetime.now().year)

@app.route("/project/<project_id>/ingestion")
def ingestion(project_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Get project info
    cur.execute("SELECT title, description FROM Project WHERE project_id=?", (project_id,))
    project_row = cur.fetchone()
    if not project_row:
        cur.close()
        conn.close()
        return "Project not found"

    project = dict(zip([column[0] for column in cur.description], project_row))

    # Get documents with tags
    cur.execute("""
        SELECT d.doc_id,
               d.title,
               d.upload_date,
               u.name AS author,
               d.status,
               STRING_AGG(t.label, ',') AS tags
        FROM Document d
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        LEFT JOIN [User] u ON d.uploader_id = u.user_id
        LEFT JOIN Document_Tag dt ON d.doc_id = dt.document_id
        LEFT JOIN Tag t ON dt.tag_id = t.tag_id
        WHERE pd.project_id = ?
        GROUP BY d.doc_id, d.title, d.upload_date, u.name, d.status
        ORDER BY d.upload_date DESC
    """, (project_id,))
    documents = dict_cursor(cur)

    cur.close()
    conn.close()

    return render_template("ingestion.html",
                           project=project,
                           project_id=project_id,
                           documents=documents)

@app.route("/project/<project_id>/document/<doc_id>/process", methods=["POST"])
def process_document(project_id, doc_id):
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    try:
        # fetch document
        cur.execute("SELECT ocr_text FROM Document WHERE doc_id = ?", (doc_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return jsonify({"success": False, "error": "Document has no text"}), 400
        doc_text = row[0]

        # fetch project
        cur.execute("SELECT title, description FROM Project WHERE project_id = ?", (project_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Project not found"}), 404
        project_title, project_description = row

        # Gemini AI
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = f"""
        Project: {project_title}
        Project Description: {project_description}

        Document Text:
        {doc_text[:6000]}

        Task: Write a concise summary (3–5 sentences) relevant to the project.
        """
        response = model.generate_content(prompt)
        summary = response.text.strip() if response and response.text else None
        if not summary:
            return jsonify({"success": False, "error": "AI did not return summary"}), 500

        # update Project_Document
        cur.execute(
            "UPDATE Project_Document SET contextual_summary = ? WHERE project_id = ? AND document_id = ?",
            (summary, project_id, doc_id)
        )
        # update Document status
        cur.execute(
            "UPDATE Document SET status = ? WHERE doc_id = ?",
            ("Complete", doc_id)
        )
        conn.commit()
        return jsonify({"success": True, "summary": summary})

    except Exception as e:
        conn.rollback()
        print("Error processing document:", e)
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        cur.close()
        conn.close()

# ------------------ Document Upload -----------------
@app.route("/project/<project_id>/upload", methods=["POST"])
def project_upload(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    file = request.files["file"]
    title = request.form["title"]
    description = request.form.get("description")
    privacy = request.form["privacy"]
    user_id = session["user_id"]

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    ext = filename.split(".")[-1].lower()
    if ext in ["pdf"]:
        doc_type = "pdf"
        ocr_text = extract_pdf_text(path)
    elif ext in ["doc", "docx"]:
        doc_type = "word"
        ocr_text = extract_word_text(path)
    elif ext in ["jpg", "jpeg", "png", "tiff"]:
        doc_type = "image"
        ocr_text = pytesseract.image_to_string(Image.open(path))
    else:
        doc_type = "other"
        ocr_text = ""

    ocr_text = re.sub(r"\n{2,}", "\n", ocr_text).strip()
    tags = generate_tags(ocr_text or description or title)

    doc_id = str(uuid.uuid4())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO Document (doc_id, uploader_id, title, description, url, upload_date, type, ocr_text, privacy_level, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, user_id, title, description, path, datetime.datetime.now(), doc_type, ocr_text, privacy, "pending"))

    cur.execute("INSERT INTO Project_Document (project_id, document_id) VALUES (?, ?)", (project_id, doc_id))

    for tag in tags:
        tag_id = get_or_create_tag(cur, tag)
        cur.execute("INSERT INTO Document_Tag (document_id, tag_id) VALUES (?, ?)", (doc_id, tag_id))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "doc_id": doc_id, "title": title, "tags": tags})

@app.route("/project/<project_id>/document/<doc_id>", methods=["GET", "POST"])
def document_detail(project_id, doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        if "delete" in request.form:
            # find project_id (redundant here since we already have it)
            cur.execute("DELETE FROM Document WHERE doc_id=?", (doc_id,))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("project_detail", project_id=project_id))

    # Get document info with uploader
    cur.execute("""
        SELECT d.doc_id, d.title, d.url, d.upload_date, d.type, d.privacy_level, d.ocr_text,
            u.name as uploader_name,
            pd.project_id,
            p.title as project_title
        FROM Document d
        LEFT JOIN [User] u ON d.uploader_id = u.user_id
        LEFT JOIN Project_Document pd ON d.doc_id = pd.document_id
        LEFT JOIN Project p ON pd.project_id = p.project_id
        WHERE d.doc_id=?
    """, (doc_id,))
    row = cur.fetchone()
    document = dict(zip([column[0] for column in cur.description], row)) if row else None

    cur.close()
    conn.close()

    if not document:
        return "Document not found"

    return render_template("document_detail.html",
                           document=document,
                           project_id=project_id)


# ------------------ Chat / AI -----------------
@app.route("/project/<project_id>/chat", methods=["POST"])
def project_chat(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_message = request.json.get("message", "")
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT d.title, d.ocr_text, GROUP_CONCAT(t.label) as tags
        FROM Document d
        LEFT JOIN Document_Tag dt ON d.doc_id = dt.document_id
        LEFT JOIN Tag t ON dt.tag_id = t.tag_id
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        WHERE pd.project_id = ?
        GROUP BY d.doc_id
    """, (project_id,))
    docs = dict_cursor(cur)
    cur.close()
    conn.close()

    context_parts = []
    for d in docs:
        tags_str = f" [tags: {d['tags']}]" if d['tags'] else ""
        context_parts.append(f"Document: {d['title']}{tags_str}\n{d.get('ocr_text','')[:1000]}")
    context = "\n\n".join(context_parts)

    try:
        prompt = f"""
        You are assisting a user with project documents.

        Project Documents:
        {context}

        User Question: {user_message}
        """
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        response = model.generate_content(prompt)
        reply = response.text.strip()
    except Exception as e:
        print("Chat error:", e)
        reply = "Sorry, I had trouble generating a response."

    return jsonify({"reply": reply})

@app.route("/project/<project_id>/chats")
def project_chats(project_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    # Fetch all chats for this project and user
    cur.execute("""
        SELECT chat_id, chat_name, created_at
        FROM Chat
        WHERE project_id=? AND user_id=?
        ORDER BY created_at DESC
    """, (project_id, user_id))
    chats = dict_cursor(cur)

    cur.close()
    conn.close()

    return render_template("project_chats.html",
                           project_id=project_id,
                           chats=chats,
                           current_year=datetime.datetime.now().year,
                           project_title=get_project_title(project_id))

@app.route("/project/<project_id>/chat/<chat_id>")
def load_chat(project_id, chat_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    # Ensure chat belongs to user and project
    cur.execute("""
        SELECT chat_id FROM Chat
        WHERE chat_id=? AND project_id=? AND user_id=?
    """, (chat_id, project_id, user_id))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify([])

    # Fetch messages
    cur.execute("""
        SELECT sender, content, created_at
        FROM ChatContent
        WHERE chat_id=?
        ORDER BY created_at ASC
    """, (chat_id,))
    messages = dict_cursor(cur)

    cur.close()
    conn.close()

    return jsonify(messages)

@app.route("/project/<project_id>/chat/<chat_id>/send", methods=["POST"])
def send_message(project_id, chat_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    message = request.json.get("message", "")

    conn = get_db()
    cur = conn.cursor()

    # --- Save user message ---
    content_id_user = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO ChatContent (content_id, chat_id, sender, content, created_at)
        VALUES (?, ?, 'user', ?, ?)
    """, (content_id_user, chat_id, message, datetime.datetime.now(datetime.timezone.utc)))
    conn.commit()

    # --- Build AI prompt from project documents ---

    cur.execute("""
        SELECT 
            d.title, 
            LEFT(d.ocr_text, 1000) AS ocr_text,
            STRING_AGG(t.label, ',') AS tags
        FROM Document d
        LEFT JOIN Document_Tag dt ON d.doc_id = dt.document_id
        LEFT JOIN Tag t ON dt.tag_id = t.tag_id
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        WHERE pd.project_id = ?
        GROUP BY d.doc_id, d.title, d.ocr_text
    """, (project_id,))
    docs = dict_cursor(cur)  # your helper to convert rows to dict

    context_parts = []
    for d in docs:
        tags_str = f" [tags: {d['tags']}]" if d['tags'] else ""
        context_parts.append(f"Document: {d['title']}{tags_str}\n{d.get('ocr_text','')}")

    lvl1_context = "\n\n".join(context_parts)

    # --- Generate AI response ---


    try:

        prompt1 = f"""

        Please return only a list of document titles that are NOT relevant to the user's question seperated by commas and nothing else.

        User Question: {message}

        Project Documents:

        {lvl1_context}

        """

        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        response = model.generate_content(prompt1)

        lvl1_reply = response.text.strip()

  
  

        lvl1_list = [name.strip() for name in lvl1_reply.split(',')]

        deny_set = set(lvl1_list)

  
  

    except Exception as e:

        print("Chat error:", e)

        reply = "Sorry, I had trouble generating a response."

  
  
  

    lvl3_info_parts = []

    for d in docs:

        if d['title'] in deny_set:

            continue

        lvl3_info_parts.append(f"Document: {d['title']}\n{d.get('ocr_text','')[:1000]}")

    lvl3_context = "\n\n".join(lvl3_info_parts)

  
  

    try:

        prompt = f"""

        You are assisting a user with project documents.

  

        Project Documents:

        {lvl3_context}

  

        User Question: {message}

        """

        model = genai.GenerativeModel("gemini-2.5-flash-lite")

        response = model.generate_content(prompt)

        reply = response.text.strip()

    except Exception as e:

        print("Chat error:", e)

        reply = "Sorry, I had trouble generating a response."

    reply = str(deny_set) + reply

    return jsonify({"reply": reply})



    # --- Save AI response ---
    content_id_ai = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO ChatContent (content_id, chat_id, sender, content, created_at)
        VALUES (?, ?, 'ai', ?, ?)
    """, (content_id_ai, chat_id, reply, datetime.datetime.now(datetime.timezone.utc)))
    conn.commit()

    cur.close()
    conn.close()

    return jsonify({"reply": reply})

@app.route("/project/<project_id>/chat/new", methods=["POST"])
def new_chat(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    chat_name = request.json.get("chat_name", "").strip()
    if not chat_name:
        return jsonify({"error": "Chat name is required"}), 400

    chat_id = str(uuid.uuid4())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO Chat (chat_id, project_id, user_id, chat_name, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (chat_id, project_id, user_id, chat_name, datetime.datetime.utcnow()))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"chat_id": chat_id, "chat_name": chat_name})

# ------------------ Main -----------------
if __name__ == "__main__":
    app.run(debug=True)
