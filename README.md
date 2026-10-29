# AI Interview Studio

An end-to-end, full-stack AI Voice Interviewer platform built with **Python Flask**, **ElevenLabs Conversational AI**, and structured **LLM-driven evaluation**.

AI Interview Studio is pre-calibrated for the **Content Creator & Content Writer** role. Candidates simply upload their resume (PDF/DOCX), and the system extracts their experience and projects, conducts a realistic spoken voice interview via an ElevenLabs AI agent, and automatically generates an objective, rubric-weighted evaluation report with downloadable PDF export.

---

## 🌟 Key Features

1. **Streamlined Setup (Resume Only)**:
   - Eliminates the need to paste or upload long Job Descriptions. The Content Creator JD and core competencies are pre-embedded directly into the AI prompts.
   - Drastically saves input tokens and prevents rate/quota limit errors.
   - Parses text-based PDFs (via `PyMuPDF`), Word documents (`python-docx`), and plain text.
   - Detects scanned or image-only PDFs and alerts users if OCR is required.
   - Uploaded documents are stored safely outside the public web root.

2. **Tailored Interview Planning**:
   - Compares the candidate's parsed resume directly against the Content Creator role requirements.
   - Automatically derives 4–6 core competencies tailored to the role (e.g., Content Strategy, SEO & Audience Research, Brand Voice Adaptation, Performance Analytics).
   - Assigns explicit percentage weights summing to 100%.
   - Prepares structured interview sections with conversational questions, expected evidence, and adaptive follow-up guidance.

3. **Spoken Voice Interaction via ElevenLabs**:
   - Employs ElevenLabs Conversational AI for natural, low-latency, bidirectional spoken dialogue.
   - Secure server-side credential generation via single-use signed URLs (`/api/interviews/<id>/conversation-credentials`). Never exposes your private `ELEVENLABS_API_KEY` to client-side code.
   - Real-time animated audio visualizer, elapsed session timer, live transcript drawer, and microphone permission checks.

4. **Objective, Rubric-Weighted Evaluation**:
   - Scores competencies on a tangible 0–5 evidence scale.
   - Correctly marks unaddressed topics as **Not Assessed** without fabricating negative scores.
   - Mathematically calculates the overall score (0–100) from assessed competency weights.
   - Provides transcript-backed quotes, concrete strengths, developmental improvement areas, practice interview questions, and learning recommendations.
   - Built-in disclaimer that evaluations provide AI-assisted feedback for human review, not automated employment decisions.

5. **Export & Management**:
   - Instant PDF report generation using `ReportLab`.
   - Comprehensive dashboard tracking interview status (Draft, Prepared, In Progress, Completed, Interrupted, Failed).
   - Idempotent finalization handling duplicate requests safely.
   - Cascading deletions for clean data lifecycle management.

---

## 🏗️ System Architecture

```
elevenlabs/
├── app/
│   ├── __init__.py                 # Flask application factory & Jinja filters
│   ├── config.py                   # Configuration & environment variable resolution
│   ├── extensions.py               # SQLAlchemy database extension
│   ├── models/
│   │   ├── __init__.py
│   │   └── interview.py            # Interview, InterviewReport, InterviewEvent models
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py            # Dashboard view & statistics
│   │   ├── interviews.py           # Setup, preparation, and live studio views
│   │   ├── reports.py              # Report display & PDF download
│   │   └── api.py                  # REST API for documents, planning, credentials, transcripts
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_parser.py      # PyMuPDF, python-docx, validation & normalization
│   │   ├── llm_service.py          # OpenAI / compatible LLM abstraction with mock fallback
│   │   ├── interview_planner.py    # Structured plan generation with Pydantic validation
│   │   ├── elevenlabs_service.py   # Signed URLs, transcript sync & webhook verification
│   │   ├── transcript_service.py   # Transcript ingestion, formatting & validation
│   │   ├── evaluation_service.py   # Rubric scoring & weighted score calculation
│   │   └── pdf_report_service.py   # Polished ReportLab PDF generation
│   ├── templates/
│   │   ├── base.html               # Main layout & ElevenLabs widget script
│   │   ├── dashboard.html          # Stats, recent interviews, actions
│   │   ├── interview_setup.html    # Drag-and-drop document upload & role config
│   │   ├── interview_preparation.html # Extracted competencies & interview flow
│   │   ├── live_interview.html     # Dedicated spoken voice studio & live transcript
│   │   └── report.html             # Score banner, competency bars, quotes & PDF export
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css          # Modern SaaS stylesheet (Indigo / Slate palette)
│   │   └── js/
│   │       ├── dashboard.js        # Interview management & deletion
│   │       ├── setup.js            # Client-side validation & extraction flow
│   │       ├── preparation.js      # Plan generation & title editing
│   │       ├── live_interview.js   # Voice connection, waveform, timers & transcript
│   │       └── report.js           # Transcript collapse/expand
│   └── prompts/
│       ├── planner.txt             # Interview planning prompt template
│       ├── interviewer.txt         # ElevenLabs agent system prompt guidelines
│       └── evaluator.txt           # Objective 0-5 rubric scoring prompt template
├── tests/
│   ├── conftest.py                 # Pytest fixtures & mock documents
│   ├── test_documents.py           # Parsing, validation & scanned PDF detection tests
│   ├── test_interviews.py          # Interview creation, planning & credentials tests
│   ├── test_evaluation.py          # Rubric math, transcript validation & PDF tests
│   └── test_security.py            # API key protection & path traversal tests
├── instance/                       # Local SQLite DB & secure uploads (gitignored)
├── requirements.txt                # Python package dependencies
├── .env.example                    # Environment variable template
├── seed_demo.py                    # Demo database seeder
└── run.py                          # Application entry point
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.11+** installed (`python --version`)
- Modern web browser (Chrome, Edge, Firefox, Safari) with microphone access enabled

### 2. Setup Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### On macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
# Windows
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env` to configure your API keys:
```ini
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-random-secret-key-here

# ElevenLabs Conversational AI
ELEVENLABS_API_KEY=xi_api_key_here
ELEVENLABS_AGENT_ID=your_elevenlabs_agent_id_here
ELEVENLABS_AUTH_MODE=signed_url
ELEVENLABS_ALLOWED_ORIGIN=http://localhost:5000

# LLM Configuration
LLM_PROVIDER=openai
LLM_API_KEY=your_openai_or_compatible_api_key
LLM_MODEL=gpt-4o-mini
```

> **Note for Offline / Testing Mode:** If you do not have an active OpenAI API key yet, you can set `LLM_PROVIDER=mock` in `.env`. The system will generate rich, realistic structured plans and evaluation reports locally.

### 5. (Optional) Seed Demo Content
Populate a sample Content Creator interview with realistic transcript turns and evaluation scores:
```bash
python seed_demo.py
```

### 6. Run the Application
```bash
python run.py
```
Open your browser at **`http://localhost:5000`**.

---

## 🎙️ Setting Up Your ElevenLabs Conversational AI Agent

To conduct live spoken voice calls with candidates, create a conversational agent in the ElevenLabs dashboard:

### Step 1: Create the Agent
1. Navigate to the [ElevenLabs Conversational AI Dashboard](https://elevenlabs.io/app/conversational-ai).
2. Click **Create Agent** (choose a blank template or standard conversational model).
3. Name your agent (e.g., **"Alex - AI Interviewer"**).

### Step 2: Configure the System Prompt & Persona
1. In the agent configuration screen, copy the prompt guidelines from **`app/prompts/interviewer.txt`** into the agent's **First Message** and **System Prompt**:
   - **First Message**:
     > *"Hello! I'm Alex, your AI interviewer today. Thank you for joining. To get started, could you briefly introduce yourself and what drew you to this role?"*
   - **System Prompt**: Paste the instructions from `app/prompts/interviewer.txt`.
2. Select a natural, conversational voice (e.g., *Chris*, *Rachel*, *Daniel*, or *Jessica*).

### Step 3: Configure Dynamic Variables
Under **Conversation Settings > Dynamic Variables**, define:
- `candidate_name` (string)
- `job_title` (string)
- `interview_id` (string)

The application automatically passes these variables when initiating the session.

### Step 4: Configure Server-Side Context Retrieval (Optional Webhook Tool)
To allow the agent to fetch the candidate's verified resume highlights and planned competency questions during the call:
1. Add a **Client / Server Tool** in ElevenLabs.
2. Set the Tool Method to `GET`.
3. Set the Tool URL to:
   ```
   https://<your-public-domain>/api/interviews/{{interview_id}}/context
   ```
   *(For local testing, use a tunneling tool like ngrok: `ngrok http 5000`).*

### Step 5: Copy Agent ID to `.env`
1. Copy the **Agent ID** from the ElevenLabs URL or Agent Settings.
2. In your `.env` file, set:
   ```ini
   ELEVENLABS_AGENT_ID=agent_xxxxxxxxxxxxxxxxxxxx
   ELEVENLABS_API_KEY=xi_api_key_xxxxxxxxxxxxxxxx
   ELEVENLABS_AUTH_MODE=signed_url
   ```
3. Restart `python run.py`.

---

## 🧪 Running Automated Tests

The test suite covers PDF/DOCX extraction, scanned PDF error handling, interview lifecycle transitions, rubric calculations, signed URL security, and cascading deletions with mocked external APIs:

```bash
python -m pytest -v
```

All 28 tests will execute in under 3 seconds without requiring paid external API tokens.

---

## 🔒 Security & Privacy Practices

- **Zero Client Credential Leakage**: The client browser never receives `ELEVENLABS_API_KEY` or `LLM_API_KEY`. Authentication uses ephemeral signed WebSocket URLs generated server-side.
- **Isolated Document Storage**: Uploaded resumes and job descriptions are stored securely in `instance/uploads/` using sanitized UUID filenames, completely isolated from public static folders.
- **Path Traversal Protection**: Filenames are strictly sanitized with `werkzeug.utils.secure_filename`.
- **Configurable Limits**: File uploads are capped at 10 MB per file.
- **Ethical AI Boundaries**: Evaluator prompts strictly evaluate the substance of candidate answers against job requirements. The model is forbidden from inferring personality, protected characteristics, accent, or speaking cadence.
- **Data Lifecycle Management**: Deleting an interview removes all associated events, transcripts, and evaluation reports.

---

## 🛠️ Troubleshooting

| Issue | Resolution |
| :--- | :--- |
| **"Microphone permission denied"** | Click the padlock or settings icon in your browser address bar and toggle Microphone to **Allow**, then refresh the page. |
| **"ElevenLabs agent not configured"** | Ensure `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` are set in `.env` without leading or trailing spaces. |
| **"LLM key is not configured"** | Add your `LLM_API_KEY` in `.env` or set `LLM_PROVIDER=mock` for offline local testing. |
| **"The uploaded PDF contains no readable text"** | The uploaded PDF is scanned or image-only. Supply a text-searchable PDF or convert it with OCR before uploading. |
| **Port 5000 already in use** | Run on a different port by setting `PORT=5050 python run.py` (or `$env:PORT=5050; python run.py` in PowerShell). |

---

## 📄 License
MIT License. Created with Google Antigravity & ElevenLabs Conversational AI.
