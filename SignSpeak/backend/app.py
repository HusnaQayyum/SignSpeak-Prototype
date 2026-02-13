import os, base64, cv2, numpy as np, io, json, time, difflib, sqlite3
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from collections import deque
from gtts import gTTS
from google import genai
from gesture import extract_landmarks_from_frame, recognize_sentence_from_sequence

# ===================== CONFIG =====================
GEMINI_KEY = "Your API KEY HERE"
client = genai.Client(api_key=GEMINI_KEY)
MODEL_ID = "gemini-2.0-flash" 

app = Flask(__name__)
app.secret_key = "signspeak_final_v9"
CORS(app, supports_credentials=True)

# --- COMPLETE LOCAL DICTIONARY ---
# Keys MUST match your sidebar .npy/.mp4 filenames EXACTLY
URDU_MAP = {
    "assalamualaikum": "اسلام علیکم", "walaikum_salaam": "وعلیکم السلام",
    "thankyou": "شکریہ", "good_morning": "صبح بخیر", "good_afternoon": "سہ پہر بخیر",
    "good_evening": "شام بخیر", "good_night": "شب بخیر", "goodbye": "خدا حافظ",
    "welcome": "خوش آمدید", "what": "کیا؟", "who": "کون؟", "come_here": "ادھر آؤ",
    "are_u_ready": "کیا آپ تیار ہیں؟", "are_u_deaf": "کیا آپ بہرے ہیں؟",
    "are_u_hungry": "کیا آپ کو بھوک لگی ہے؟", "close_the_door": "دروازہ بند کریں",
    "need_help": "مجھے مدد چاہیے", "call_doctor": "ڈاکٹر کو بلائیں",
    "i_am_student": "میں ایک طالب علم ہوں", "go_away": "چلے جاؤ", "stay_here": "یہاں رہو",
    "how_much": "کتنے پیسے؟", "congrates": "مبارک ہو", "excuse_me": "معاف کیجئے گا"
}

frame_buffer = deque(maxlen=60)
detected_words = []
last_word_time = 0

def super_clean(text): return "".join(filter(str.isalnum, text.lower()))

@app.route("/")
def home(): return "SignSpeak API Active"

# --- LEFT SIDE: SIGN TO SPEECH ---
@app.route("/api/recognize-gesture", methods=["POST"])
def recognize_gesture():
    global detected_words, last_word_time
    try:
        # 1. Check for Pause (Gemini Synthesis)
        if detected_words and (time.time() - last_word_time > 1.8):
            phrase = " ".join(detected_words)
            words_to_process = list(detected_words)
            detected_words = [] 
            frame_buffer.clear()

            try:
                # Ask Gemini to refine the sentence
                prompt = f"The user signed these keywords: {words_to_process}. Formulate ONE natural, polite Urdu sentence and its English translation. Return ONLY JSON: {{\"urdu\": \"...\", \"english\": \"...\"}}"
                response = client.models.generate_content(model=MODEL_ID, contents=prompt)
                clean_json = response.text.strip().replace('```json', '').replace('```', '').strip()
                ai_data = json.loads(clean_json)
                urdu_text, eng_text = ai_data['urdu'], ai_data['english']
            except:
                # FALLBACK: Local Dictionary concatenation
                urdu_text = " ".join([URDU_MAP.get(w, w) for w in words_to_process])
                eng_text = phrase.upper().replace("_", " ")

            tts = gTTS(text=urdu_text, lang='ur')
            fp = io.BytesIO(); tts.write_to_fp(fp); fp.seek(0)
            audio = base64.b64encode(fp.read()).decode()
            return jsonify({"success": True, "is_final": True, "gesture": eng_text, "urdu_text": urdu_text, "audio": audio})

        # 2. Process Image
        data = request.json
        nparr = np.frombuffer(base64.b64decode(data['frame'].split(',')[1]), np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        lms = extract_landmarks_from_frame(frame)
        if lms is not None: frame_buffer.append(lms)

        if len(frame_buffer) >= 12:
            res, score = recognize_sentence_from_sequence(list(frame_buffer))
            if res and score < 8.0:
                if not detected_words or detected_words[-1] != res:
                    detected_words.append(res)
                    last_word_time = time.time()
                frame_buffer.clear()
                return jsonify({"success": True, "is_final": False, "interim": " ".join(detected_words)})
        return jsonify({"success": False})
    except: return jsonify({"success": False})

# --- RIGHT SIDE: SPEECH TO SIGN (AVATAR) ---
@app.route("/api/text-to-sign", methods=["POST"])
def text_to_sign():
    try:
        raw_text = request.json.get("text", "").lower().strip()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        signs_dir = os.path.normpath(os.path.join(base_dir, "..", "frontend", "assets", "signs"))
        actual_files = [f.replace('.mp4', '') for f in os.listdir(signs_dir) if f.endswith('.mp4')]

        # 1. Local Search (Typos)
        matches = difflib.get_close_matches(super_clean(raw_text), [super_clean(f) for f in actual_files], n=1, cutoff=0.5)
        if matches:
            real_name = next(f for f in actual_files if super_clean(f) == matches[0])
            return jsonify({"success": True, "sequence": [{"word": real_name, "url": f"assets/signs/{real_name}.mp4"}]})

        # 2. Gemini Semantic Search
        try:
            prompt = f"Simplify: '{raw_text}' to keywords from: {actual_files}. Return keywords only."
            response = client.models.generate_content(model=MODEL_ID, contents=prompt)
            keywords = response.text.lower().strip().split()
            sequence = [{"word": k, "url": f"assets/signs/{k}.mp4"} for k in keywords if k in actual_files]
            if sequence: return jsonify({"success": True, "sequence": sequence})
        except: pass

        return jsonify({"success": False})
    except: return jsonify({"success": False})

if __name__ == "__main__":

    app.run(debug=False, port=5000, threaded=False)
