import os
import io
import zipfile
import json
import sqlite3
import hashlib
import hmac
import base64
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Depends, Response
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import status
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel
from datetime import datetime
import logging
from data_processing import calculate_moving_average
from dotenv import load_dotenv
from pathlib import Path

from services.openrouter import get_openrouter_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(Path(BASE_DIR) / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "dev-session-secret")
DATABASE_URL = os.getenv("DATABASE_URL")
try:
    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore
except Exception:
    psycopg2 = None  # type: ignore

try:
    client = get_openrouter_client()
    logger.info("OpenRouter client initialized")
except RuntimeError as exc:
    logger.error("Failed to initialize OpenRouter client: %s", exc)
    client = None

# Импорты из data_processing (обработка возможных ошибок)
try:
    from data_processing import (
        baseline_als,
        smooth_signal,
        normalize_snv,
        find_signal_peaks,
        filter_frequency_range,
        parse_esp_file,
        calculate_mean_std, 
        calculate_boxplot_stats,
        parse_txt_file,
        parse_csv_file,
        parse_any_spectral_file
    )
except ImportError as e:
    logger.error(f"Ошибка импорта data_processing: {e}")
    # Заглушки функций на случай ошибки импорта
    def baseline_als(*args, **kwargs): return np.zeros_like(args[0])
    def smooth_signal(*args, **kwargs): return args[0]
    def normalize_snv(*args, **kwargs): return args[0]
    def find_signal_peaks(*args, **kwargs): return [], {}
    def filter_frequency_range(*args, **kwargs): return args[0], args[1]
    def parse_esp_file(*args, **kwargs): return [], []
    def calculate_mean_std(*args, **kwargs): return [], []
    def calculate_boxplot_stats(*args, **kwargs): return []
    def parse_txt_file(*args, **kwargs): return [], []
    def parse_csv_file(*args, **kwargs): return [], []
    def parse_any_spectral_file(*args, **kwargs): return [], []

# Инициализация FastAPI приложения
app = FastAPI(title="Spectral Processing API", version="1.0.0")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_DB_PATH = os.getenv("USER_DB_PATH", os.path.join(BASE_DIR, "users.db"))
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(60 * 60 * 24 * 7)))
MAX_PRESET_SLOTS = 5

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    max_age=SESSION_MAX_AGE,
    session_cookie="spectral_session",
    same_site="lax",
    https_only=False
)

logger.info("Base directory: %s", BASE_DIR)

# Проверяем существование папок
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

logger.info(f"Templates directory exists: {os.path.exists(TEMPLATES_DIR)}")
logger.info(f"Static directory exists: {os.path.exists(STATIC_DIR)}")

# Создаем папки если они не существуют
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)



class _DBResult:
    def __init__(self, driver: str, cursor):
        self._driver = driver
        self._cursor = cursor
        self.rowcount = getattr(cursor, 'rowcount', -1)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class DBConnection:
    def __init__(self, driver: str, conn):
        self.driver = driver
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()):  # returns _DBResult
        if self.driver == 'postgres':
            sql = sql.replace('?', '%s')
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # type: ignore
            cur.execute(sql, params)
            return _DBResult(self.driver, cur)
        else:
            cur = self._conn.execute(sql, params)
            return _DBResult(self.driver, cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def _using_postgres() -> bool:
    return bool(DATABASE_URL) and psycopg2 is not None  # type: ignore


def init_user_db() -> None:
    if _using_postgres():
        conn = psycopg2.connect(DATABASE_URL)  # type: ignore
        db = DBConnection('postgres', conn)
        try:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_presets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 5),
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, slot),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            db.commit()
        finally:
            db.close()
    else:
        conn = sqlite3.connect(USER_DB_PATH)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 5),
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, slot)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

def hash_password(password: str) -> Tuple[str, str]:
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return base64.b64encode(salt).decode("utf-8"), base64.b64encode(hashed).decode("utf-8")

def verify_password(password: str, salt_b64: str, hash_b64: str) -> bool:
    salt = base64.b64decode(salt_b64.encode("utf-8"))
    expected_hash = base64.b64decode(hash_b64.encode("utf-8"))
    test_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return hmac.compare_digest(expected_hash, test_hash)

def get_user_by_username(username: str):
    if DATABASE_URL and psycopg2 is not None:
        conn = DBConnection('postgres', psycopg2.connect(DATABASE_URL))  # type: ignore
    else:
        raw = sqlite3.connect(USER_DB_PATH)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        conn = DBConnection('sqlite', raw)
    try:
        cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cursor.fetchone()
    finally:
        conn.close()

def create_user(username: str, password: str) -> None:
    salt, password_hash = hash_password(password)
    if DATABASE_URL and psycopg2 is not None:
        conn = DBConnection('postgres', psycopg2.connect(DATABASE_URL))  # type: ignore
    else:
        raw = sqlite3.connect(USER_DB_PATH)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        conn = DBConnection('sqlite', raw)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, salt, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def get_db_connection():
    if DATABASE_URL and psycopg2 is not None:
        return DBConnection('postgres', psycopg2.connect(DATABASE_URL))  # type: ignore
    raw = sqlite3.connect(USER_DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return DBConnection('sqlite', raw)

def require_user(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
def _get_user_row_or_401(username: str):
    user_row = get_user_by_username(username)
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_row


def _validate_preset_slot(slot: int) -> None:
    if not 1 <= slot <= MAX_PRESET_SLOTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slot must be between 1 and {MAX_PRESET_SLOTS}",
        )


try:
    init_user_db()
    logger.info("User database ready at %s", USER_DB_PATH)
except Exception as auth_init_error:
    logger.error("Failed to initialize user database: %s", auth_init_error)
    raise

# Монтирование статических файлов и шаблонов
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Модели Pydantic для валидации данных
class ProcessDataRequest(BaseModel):
    frequencies: List[List[float]]
    amplitudes: List[List[float]]
    min_freq: Optional[float] = 0
    max_freq: Optional[float] = 10000
    remove_baseline: Optional[bool] = False
    apply_smoothing: Optional[bool] = False
    normalize: Optional[bool] = False
    find_peaks: Optional[bool] = False
    calculate_boxplot: Optional[bool] = False
    calculate_mean_std: Optional[bool] = False
    width: Optional[int] = 1
    prominence: Optional[int] = 1
    lam: Optional[int] = 1000
    p: Optional[float] = 0.001
    window_length: Optional[int] = 25
    polyorder: Optional[int] = 1
    show_moving_average: Optional[bool] = False
    moving_average_window: Optional[int] = 10

class ExportDataRequest(BaseModel):
    frequencies: List[List[float]]
    amplitudes: List[List[float]]
    fileNames: List[str]
    params: Dict[str, Any]

class ExportMeanRequest(BaseModel):
    frequencies: List[float]
    mean_amplitude: List[float]
    params: Optional[Dict[str, Any]] = {}
    
    
    
    
    
    
    
    
    
    
    
    
class AIAnalysisRequest(BaseModel):
    frequencies: List[float]
    amplitudes: List[float]
    processing_params: Dict[str, Any]
    sample_info: Optional[Dict[str, Any]] = None  # Дополнительная информация об образце
    analysis_type: str = "detailed_spectral_analysis"
    
    
    
    
    
    
    
    
    
    
    
    
    
    

class PresetSaveRequest(BaseModel):
    name: str
    payload: Dict[str, Any]

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render login form or redirect authenticated users."""
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    registered = request.query_params.get("registered")
    success_message = "Регистрация прошла успешно. Теперь можно войти." if registered else None
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "success": success_message, "username": ""})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Validate credentials and issue a session."""
    username = username.strip()
    if not username or not password:
        context = {"request": request, "error": "Введите логин и пароль", "success": None, "username": username}
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    record = get_user_by_username(username)
    if not record or not verify_password(password, record["salt"], record["password_hash"]):
        context = {"request": request, "error": "Неверный логин или пароль", "success": None, "username": username}
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    request.session["user"] = username
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Render registration form or redirect authenticated users."""
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse("register.html", {"request": request, "error": None, "username": ""})


@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    """Create a new account with simple validation."""
    username = username.strip()
    if len(username) < 3:
        context = {"request": request, "error": "Логин должен содержать минимум 3 символа", "username": username}
        return templates.TemplateResponse("register.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    if len(password) < 6:
        context = {"request": request, "error": "Пароль должен содержать минимум 6 символов", "username": username}
        return templates.TemplateResponse("register.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    if password != confirm_password:
        context = {"request": request, "error": "Пароли не совпадают", "username": username}
        return templates.TemplateResponse("register.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    if get_user_by_username(username):
        context = {"request": request, "error": "Такой пользователь уже существует", "username": username}
        return templates.TemplateResponse("register.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        create_user(username, password)
    except Exception:
        context = {"request": request, "error": "Не удалось создать пользователя. Попробуйте другой логин", "username": username}
        return templates.TemplateResponse("register.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    return RedirectResponse(url="/login?registered=1", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
async def logout(request: Request):
    """Clear the session cookie."""
    request.session.pop("user", None)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the landing page for guests and authenticated users."""
    user = request.session.get("user")
    context = {
        "request": request,
        "user": user,
        "is_authenticated": bool(user),
    }


    try:
        return templates.TemplateResponse("index.html", context)
    except Exception as e:
        logger.error(f"Error loading template: {e}")
        return HTMLResponse(content=f"""
        <html>
            <body>
                <h1>Ошибка загрузки шаблона</h1>
                <p>Проверьте наличие файла index.html в папке templates</p>
                <p>Ошибка: {str(e)}</p>
            </body>
        </html>
        """)

@app.get("/test")
async def test_endpoint():
    """
    Тестовый endpoint для проверки работы сервера.
    """
    return {"message": "Server is working!", "status": "OK"}

@app.get("/check-files")
async def check_files():
    """
    Проверка существования файлов.
    """
    files = {
        "index.html": os.path.exists(os.path.join(TEMPLATES_DIR, "index.html")),
        "style.css": os.path.exists(os.path.join(STATIC_DIR, "style.css")),
        "app.js": os.path.exists(os.path.join(STATIC_DIR, "app.js"))
    }
    return files

@app.post("/upload_files")
async def upload_files(files: List[UploadFile] = File(...)):
    """
    Загрузка файлов и извлечение данных частот и амплитуд.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Файлы не найдены")

    all_frequencies = []
    all_amplitudes = []
    file_names = []

    try:
        for file in files:
            if file.filename == "":
                raise HTTPException(status_code=400, detail="Один из файлов не имеет имени")

            raw_content = await file.read()
            decoded_content = None
            for encoding in ("utf-8", "cp1251", "latin-1"):
                try:
                    decoded_content = raw_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

            if decoded_content is None:
                raise HTTPException(status_code=400, detail=f'Не удалось декодировать файл {file.filename}. Поддерживаются только текстовые файлы.')

            try:
                frequencies, amplitudes = parse_any_spectral_file(decoded_content)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f'Ошибка при обработке файла {file.filename}: {str(e)}')

            # Сохраняем результаты
            all_frequencies.append(frequencies)
            all_amplitudes.append(amplitudes)
            file_names.append(file.filename)

        return {
            'message': 'Файлы успешно загружены!',
            'files': file_names,
            'frequencies': all_frequencies,
            'amplitudes': all_amplitudes
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Ошибка обработки файлов: {str(e)}')

@app.post("/process_data")
async def process_data(payload: ProcessDataRequest):
    try:
        # Получаем данные из запроса
        frequencies_list = payload.frequencies
        amplitudes_list = payload.amplitudes
        
        # Обработка данных
        allFrequencies = []
        allAmplitudes = []
        peaks_list = []
        peaks_values_list = []
        peaks_info_list = []

        for frequencies, amplitudes in zip(frequencies_list, amplitudes_list):
            # Конвертируем в numpy arrays
            freq_array = np.array(frequencies)
            amp_array = np.array(amplitudes)

            # Фильтрация по частотам
            freq_array, amp_array = filter_frequency_range(
                freq_array, amp_array, payload.min_freq, payload.max_freq
            )

            # Удаление базовой линии
            if payload.remove_baseline:
                amp_array -= baseline_als(amp_array, payload.lam, payload.p)

            # Сглаживание
            if payload.apply_smoothing:
                amp_array = smooth_signal(amp_array, payload.window_length, payload.polyorder)

            # Нормализация
            if payload.normalize:
                amp_array = normalize_snv(amp_array)

            # Поиск пиков
            peaks = []
            peaks_values = []
            peaks_info = []
            if payload.find_peaks:
                peaks, _ = find_signal_peaks(amp_array, width=payload.width, prominence=payload.prominence)
                peaks_values = amp_array[peaks] if len(peaks) > 0 else []
                if len(peaks) > 0:
                    for order, peak_idx in enumerate(peaks, start=1):
                        peaks_info.append({
                            'index': int(peak_idx),
                            'order': order,
                            'frequency': float(freq_array[peak_idx]),
                            'amplitude': float(amp_array[peak_idx])
                        })

            # Сохраняем результаты
            allFrequencies.append(freq_array.tolist())
            allAmplitudes.append(amp_array.tolist())
            peaks_list.append(peaks.tolist() if hasattr(peaks, 'tolist') else peaks)
            peaks_values_list.append(peaks_values.tolist() if hasattr(peaks_values, 'tolist') else peaks_values)
            peaks_info_list.append(peaks_info)

        # Расчет статистики
        boxplot_stats = []
        if payload.calculate_boxplot and len(allAmplitudes) > 0:
            boxplot_stats = calculate_boxplot_stats([np.array(amp) for amp in allAmplitudes])

        mean_amplitude, std_amplitude = [], []
        if payload.calculate_mean_std and len(allAmplitudes) > 0:
            mean_amplitude, std_amplitude = calculate_mean_std([np.array(amp) for amp in allAmplitudes])
            mean_amplitude = mean_amplitude.tolist() if hasattr(mean_amplitude, 'tolist') else mean_amplitude
            std_amplitude = std_amplitude.tolist() if hasattr(std_amplitude, 'tolist') else std_amplitude
        moving_averages = []
        
        if payload.show_moving_average:  # Добавьте этот параметр в модель
            for amplitudes in allAmplitudes:
                moving_avg = calculate_moving_average(amplitudes, payload.moving_average_window)
                moving_averages.append(moving_avg.tolist())
        
        return {
            'frequencies': allFrequencies,
            'processed_amplitudes': allAmplitudes,
            'peaks': peaks_list,
            'peaks_values': peaks_values_list,
            'peaks_info': peaks_info_list,
            'mean_amplitude': mean_amplitude,
            'boxplot_stats': boxplot_stats,
            'std_amplitude': std_amplitude,
            'moving_averages': moving_averages

        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка обработки данных: {str(e)}")

import zipfile
import io
import numpy as np
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any

# Модель Pydantic для валидации данных
class ExportDataRequest(BaseModel):
    frequencies: List[List[float]]
    amplitudes: List[List[float]]
    fileNames: List[str]
    params: Dict[str, Any]

class ExportMeanRequest(BaseModel):
    frequencies: List[float]
    mean_amplitude: List[float]
    params: Optional[Dict[str, Any]] = {}

@app.post("/export_processed_data")
async def export_processed_data(payload: ExportDataRequest):
    """
    Экспорт обработанных данных в ZIP-архив
    """
    try:
        frequencies = payload.frequencies
        amplitudes = payload.amplitudes
        file_names = payload.fileNames
        params = payload.params

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, (freq, ampl, name) in enumerate(zip(frequencies, amplitudes, file_names)):
                base_name = f"spectrum_{i+1}" if not name else name.split('.')[0]
                file_name = f"{base_name}_processed.txt"
                
                content = "# Processed spectral data (after transformations)\n"
                content += f"# Original file: {name}\n"
                content += "# Processing parameters:\n"
                for param, value in params.items():
                    content += f"# {param}: {value}\n"
                content += "# Wavenumber (cm⁻¹)\tIntensity (a.u.)\n"
                
                for wavenumber, intensity in zip(freq, ampl):
                    content += f"{wavenumber}\t{intensity}\n"
                
                zip_file.writestr(file_name, content)
            
            # Файл с метаданными
            meta_content = "# Processing metadata\n"
            meta_content += f"# Export date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            meta_content += "# Applied transformations:\n"
            if params.get('remove_baseline'):
                meta_content += "# - Baseline removal applied\n"
            if params.get('apply_smoothing'):
                meta_content += "# - Smoothing applied\n"
            if params.get('normalize'):
                meta_content += "# - Normalization applied\n"
            meta_content += "# Parameters:\n"
            for param, value in params.items():
                meta_content += f"# {param}: {value}\n"
            
            zip_file.writestr("processing_metadata.txt", meta_content)

        zip_buffer.seek(0)
        
        return StreamingResponse(
            io.BytesIO(zip_buffer.getvalue()),
            media_type='application/zip',
            headers={
                'Content-Disposition': 'attachment; filename=processed_spectra.zip'
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка экспорта: {str(e)}")

@app.post("/export_mean_spectrum")
async def export_mean_spectrum(payload: ExportMeanRequest):
    """
    Экспорт среднего спектра в CSV
    """
    try:
        frequencies = np.array(payload.frequencies)
        mean_amplitude = np.array(payload.mean_amplitude)
        params = payload.params

        # Создаем CSV-строку с метаданными
        metadata_lines = ["# Metadata"]
        for param, value in params.items():
            metadata_lines.append(f"# {param}: {value}")
        metadata_str = "; ".join(metadata_lines)

        csv_data = f"{metadata_str}\n#frequency,mean_amplitude\n"
        csv_data += "\n".join([f"{freq},{amp}" for freq, amp in zip(frequencies, mean_amplitude)])

        return StreamingResponse(
            io.StringIO(csv_data),
            media_type='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=mean_spectrum.csv'
            }
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))














@app.post("/analyze_spectrum")
async def analyze_spectrum(payload: AIAnalysisRequest):
    """
    Анализ спектра с помощью DeepSeek AI
    """
    if client is None:
        raise HTTPException(status_code=500, detail="AI analysis service is not configured")

    try:
        # Находим основные пики в спектре
        import numpy as np
        from scipy.signal import find_peaks
        
        amplitudes_np = np.array(payload.amplitudes)
        frequencies_np = np.array(payload.frequencies)
        
        # Находим пики с значимой интенсивностью
        peaks, properties = find_peaks(amplitudes_np, 
                                      height=np.percentile(amplitudes_np, 75),
                                      prominence=0.1*np.max(amplitudes_np))
        
        # Сортируем пики по интенсивности
        peak_intensities = amplitudes_np[peaks]
        sorted_indices = np.argsort(peak_intensities)[::-1]  # Сортировка по убыванию
        top_peaks = peaks[sorted_indices][:10]  # Берем 10 самых интенсивных пиков
        
        # Формируем детальную информацию о пиках
        peaks_info = []
        for i, peak_idx in enumerate(top_peaks):
            peaks_info.append({
                'position': float(frequencies_np[peak_idx]),
                'intensity': float(amplitudes_np[peak_idx]),
                'relative_intensity': float(amplitudes_np[peak_idx] / np.max(amplitudes_np))
            })
        
        # Определяем тип спектра на основе диапазона частот
        freq_range = max(frequencies_np) - min(frequencies_np)
        if freq_range < 1000 and max(frequencies_np) < 1000:
            spectrum_type = "Рамановская спектроскопия"
        elif 400 <= min(frequencies_np) and max(frequencies_np) <= 4000:
            spectrum_type = "ИК-спектроскопия"
        elif max(frequencies_np) > 10000:
            spectrum_type = "УФ-видимая спектроскопия"
        else:
            spectrum_type = "Неизвестный тип спектра"
        
        # Формируем промпт для анализа
        prompt = f"""
        Ты эксперт-спектроскопист с 20-летним опытом анализа спектральных данных.
        Проанализируй предоставленные спектральные данные и дай максимально подробный экспертный анализ.

        ОБЩАЯ ИНФОРМАЦИЯ О СПЕКТРЕ:
        - Тип спектра: {spectrum_type}
        - Количество точек данных: {len(payload.frequencies)}
        - Диапазон частот: {min(frequencies_np):.2f} - {max(frequencies_np):.2f} см⁻¹
        - Диапазон амплитуд: {min(amplitudes_np):.6f} - {max(amplitudes_np):.6f}
        - Медианная интенсивность: {np.median(amplitudes_np):.6f}

        ОСНОВНЫЕ ПИКИ (отсортированы по интенсивности):
        {json.dumps(peaks_info, indent=2)}

        ПАРАМЕТРЫ ОБРАБОТКИ ДАННЫХ:
        {json.dumps(payload.processing_params, indent=2)}

        ПРОФЕССИОНАЛЬНЫЙ АНАЛИЗ:
        1. ДЕТАЛЬНАЯ ИНТЕРПРЕТАЦИЯ КАЖДОГО ПИКА:
           - Для каждого пика укажи возможные функциональные группы или химические связи
           - Укажи характерные области спектра для каждого пика
           - Оцени силу и специфичность каждого пика

        2. ВЕРОЯТНЫЕ СОЕДИНЕНИЯ ИЛИ МАТЕРИАЛЫ:
           - Предположи 3-5 наиболее вероятных соединений/материалов
           - Объясни, какие особенности спектра поддерживают каждое предположение
           - Укажи степень уверенности для каждого предположения

        3. КАЧЕСТВЕННЫЙ АНАЛИЗ СПЕКТРА:
           - Оцени качество данных (шумы, артефакты, разрешение)
           - Определи, есть ли признаки неорганических компонентов
           - Определи, есть ли признаки органических компонентов

        4. РЕКОМЕНДАЦИИ ПО ДАЛЬНЕЙШЕМУ АНАЛИЗУ:
           - Какие дополнительные измерения помогут уточнить анализ
           - Какие методы подтверждения рекомендованы
           - На какие конкретные спектральные базы данных стоит обратить внимание

        5. ОГРАНИЧЕНИЯ АНАЛИЗА:
           - Укажи ограничения текущего анализа
           - Какая дополнительная информация могла бы улучшить анализ

        Предоставь ответ на русском языке в формате профессионального научного отчёта.
        Будь максимально точным и детальным, но избегай излишней спекуляции.
        """

        # Отправляем запрос к DeepSeek через OpenRouter
        response = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
            messages=[
                {"role": "system", "content": "Ты ведущий эксперт в области аналитической химии и спектроскопии с глубокими знаниями во всех типах спектроскопических методов (ИК, Раман, УФ-видимая, ЯМР и др.). Твоя задача - предоставлять максимально точный и детальный анализ спектральных данных."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000,
            temperature=0.3  # Низкая температура для более детерминированных ответов
        )

        analysis = response.choices[0].message.content

        return {
            "analysis": analysis, 
            "success": True,
            "peaks_identified": len(peaks_info),
            "spectrum_type": spectrum_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка AI анализа: {str(e)}")
        return {"analysis": f"Ошибка анализа: {str(e)}", "success": False}

















@app.get("/presets")
async def list_presets(current_user: str = Depends(require_user)):
    user_row = _get_user_row_or_401(current_user)
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT slot, name, updated_at FROM saved_presets WHERE user_id = ? ORDER BY slot",
            (user_row["id"],),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"slot": row["slot"], "name": row["name"], "updated_at": row["updated_at"]}
        for row in rows
    ]


@app.post("/presets/{slot}")
async def save_preset(slot: int, preset: PresetSaveRequest, current_user: str = Depends(require_user)):
    _validate_preset_slot(slot)
    user_row = _get_user_row_or_401(current_user)
    preset_name = (preset.name or "").strip()
    if not preset_name:
        preset_name = f"Пресет {slot}"
    timestamp = datetime.utcnow().isoformat()
    conn = get_db_connection()
    try:
        conn.execute(
            '''
            INSERT INTO saved_presets (user_id, slot, name, payload, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, slot) DO UPDATE SET
                name = excluded.name,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            ''',
            (
                user_row["id"],
                slot,
                preset_name,
                json.dumps(preset.payload, ensure_ascii=False),
                timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"slot": slot, "name": preset_name, "updated_at": timestamp}


@app.get("/presets/{slot}")
async def load_preset(slot: int, current_user: str = Depends(require_user)):
    _validate_preset_slot(slot)
    user_row = _get_user_row_or_401(current_user)
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT slot, name, payload, updated_at FROM saved_presets WHERE user_id = ? AND slot = ?",
            (user_row["id"], slot),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError:
        payload = {}
    return {
        "slot": row["slot"],
        "name": row["name"],
        "payload": payload,
        "updated_at": row["updated_at"],
    }


@app.delete("/presets/{slot}")
async def delete_preset(slot: int, current_user: str = Depends(require_user)):
    _validate_preset_slot(slot)
    user_row = _get_user_row_or_401(current_user)
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM saved_presets WHERE user_id = ? AND slot = ?",
            (user_row["id"], slot),
        )
        conn.commit()
    finally:
        conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


if __name__ == '__main__':
    import uvicorn, os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    




























