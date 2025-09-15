import os
import io
import zipfile
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging
from data_processing import calculate_moving_average

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        parse_csv_file
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

# Получаем абсолютный путь к текущей директории
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger.info(f"Base directory: {BASE_DIR}")

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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Отображение главной страницы.
    """
    try:
        return templates.TemplateResponse("index.html", {"request": request})
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

            filename = file.filename.lower()
            content = (await file.read()).decode('utf-8')

            frequencies = []
            amplitudes = []

            if filename.endswith('.esp'):
                try:
                    frequencies, amplitudes = parse_esp_file(content)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f'Ошибка при обработке файла {file.filename}: {str(e)}')
            elif filename.endswith('.txt'):
                frequencies, amplitudes = parse_txt_file(content)
            elif filename.endswith('.csv'):
                frequencies, amplitudes = parse_csv_file(content)
            else:
                raise HTTPException(status_code=400, detail=f'Неподдерживаемый тип файла: {file.filename}')

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
async def process_data(request: ProcessDataRequest):
    try:
        # Получаем данные из запроса
        frequencies_list = request.frequencies
        amplitudes_list = request.amplitudes
        
        # Обработка данных
        allFrequencies = []
        allAmplitudes = []
        peaks_list = []
        peaks_values_list = []

        for frequencies, amplitudes in zip(frequencies_list, amplitudes_list):
            # Конвертируем в numpy arrays
            freq_array = np.array(frequencies)
            amp_array = np.array(amplitudes)

            # Фильтрация по частотам
            freq_array, amp_array = filter_frequency_range(
                freq_array, amp_array, request.min_freq, request.max_freq
            )

            # Удаление базовой линии
            if request.remove_baseline:
                amp_array -= baseline_als(amp_array, request.lam, request.p)

            # Сглаживание
            if request.apply_smoothing:
                amp_array = smooth_signal(amp_array, request.window_length, request.polyorder)

            # Нормализация
            if request.normalize:
                amp_array = normalize_snv(amp_array)

            # Поиск пиков
            peaks = []
            peaks_values = []
            if request.find_peaks:
                peaks, _ = find_signal_peaks(amp_array, width=request.width, prominence=request.prominence)
                peaks_values = amp_array[peaks] if len(peaks) > 0 else []

            # Сохраняем результаты
            allFrequencies.append(freq_array.tolist())
            allAmplitudes.append(amp_array.tolist())
            peaks_list.append(peaks.tolist() if hasattr(peaks, 'tolist') else peaks)
            peaks_values_list.append(peaks_values.tolist() if hasattr(peaks_values, 'tolist') else peaks_values)

        # Расчет статистики
        boxplot_stats = []
        if request.calculate_boxplot and len(allAmplitudes) > 0:
            boxplot_stats = calculate_boxplot_stats([np.array(amp) for amp in allAmplitudes])

        mean_amplitude, std_amplitude = [], []
        if request.calculate_mean_std and len(allAmplitudes) > 0:
            mean_amplitude, std_amplitude = calculate_mean_std([np.array(amp) for amp in allAmplitudes])
            mean_amplitude = mean_amplitude.tolist() if hasattr(mean_amplitude, 'tolist') else mean_amplitude
            std_amplitude = std_amplitude.tolist() if hasattr(std_amplitude, 'tolist') else std_amplitude
        moving_averages = []
        
        if request.show_moving_average:  # Добавьте этот параметр в модель
            for amplitudes in allAmplitudes:
                moving_avg = calculate_moving_average(amplitudes, request.moving_average_window)
                moving_averages.append(moving_avg.tolist())
        
        return {
            'frequencies': allFrequencies,
            'processed_amplitudes': allAmplitudes,
            'peaks': peaks_list,
            'peaks_values': peaks_values_list,
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
async def export_processed_data(request: ExportDataRequest):
    """
    Экспорт обработанных данных в ZIP-архив
    """
    try:
        frequencies = request.frequencies
        amplitudes = request.amplitudes
        file_names = request.fileNames
        params = request.params

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
async def export_mean_spectrum(request: ExportMeanRequest):
    """
    Экспорт среднего спектра в CSV
    """
    try:
        frequencies = np.array(request.frequencies)
        mean_amplitude = np.array(request.mean_amplitude)
        params = request.params

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


if __name__ == '__main__':
    import uvicorn, os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    import os
from openai import OpenAI
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Инициализация клиента DeepSeek
deepseek_client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_API_BASE')
)

class SpectrumAnalysisRequest(BaseModel):
    frequencies: List[float]
    amplitudes: List[float]
    spectrum_type: Optional[str] = "unknown"
    additional_context: Optional[str] = ""

@app.post("/analyze_spectrum")
async def analyze_spectrum(request: SpectrumAnalysisRequest):
    """
    Анализ спектра с помощью DeepSeek AI
    """
    try:
        # Подготовка данных для анализа
        spectrum_data = []
        for i, (freq, amp) in enumerate(zip(request.frequencies, request.amplitudes)):
            if i % 10 == 0:  # Берем каждую 10-ю точку для экономии токенов
                spectrum_data.append(f"{freq:.2f} cm⁻¹: {amp:.4f}")
        
        spectrum_text = "\n".join(spectrum_data[:50])  # Ограничиваем количество точек
        
        # Создание промпта для анализа
        prompt = f"""
        Проанализируйте следующий спектр (тип: {request.spectrum_type}):
        
        {spectrum_text}
        
        {request.additional_context}
        
        Проанализируйте:
        1. Основные пики и их возможную природу
        2. Характерные особенности спектра
        3. Возможные соединения или материалы
        4. Качество данных и артефакты
        5. Рекомендации по дальнейшему анализу
        
        Ответ предоставьте в формате Markdown.
        """
        
        # Запрос к DeepSeek API
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "Ты эксперт по спектроскопии. Анализируй спектры и предоставляй детальный анализ на русском языке."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        analysis = response.choices[0].message.content
        
        return {
            "analysis": analysis,
            "model": "deepseek-chat",
            "tokens_used": response.usage.total_tokens
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")