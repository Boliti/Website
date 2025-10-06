let allFrequencies = [];
let allAmplitudes = [];
let fileNames = [];
let processedData = {
    frequencies: [],
    amplitudes: [],
    fileNames: [],
    params: {}
};

let peakTableData = null;
let draggedFiles = [];
let latestMeanAmplitude = [];
const PRESET_DEFAULT_NAME = 'Свободно';
let presetState = {};
let presetsLocked = false;
console.log('app.js loaded successfully');

function initLegendHover() {}

// Централизованно обрабатывает ответы API, требующие авторизации
// Централизованно обрабатываем ответы API, требующие авторизации
function redirectIfUnauthorized(response, message) {
    if (response.status === 401) {
        showAuthBanner(message || 'Требуется авторизация.');
        return true;
    }
    return false;
}

// Показывает баннер с текстом о необходимой авторизации
function showAuthBanner(message) {
    const banner = document.getElementById('auth-banner');
    if (!banner) {
        return;
    }
    banner.textContent = message;
    banner.classList.remove('hidden');
}

// Скрывает баннер авторизации
function hideAuthBanner() {
    const banner = document.getElementById('auth-banner');
    if (!banner) {
        return;
    }
    banner.classList.add('hidden');
}

// Обновляет текст подсказки под панелью пресетов
function updatePresetsHint(text) {
    const hint = document.getElementById('presets-hint');
    if (!hint) {
        return;
    }
    hint.textContent = text;
}

// Массово блокирует или разблокирует кнопки панелей пресетов
function updatePresetButtonsDisabled(disabled) {
    document.querySelectorAll('.preset-slot-actions button').forEach((button) => {
        button.disabled = disabled;
    });
}

// Переводит панель пресетов в заблокированное состояние
function lockPresetPanel(message) {
    presetsLocked = true;
    updatePresetButtonsDisabled(true);
    updatePresetsHint(message || 'Войдите, чтобы сохранять пресеты.');
}

// Разрешает взаимодействие с панелью пресетов
function unlockPresetPanel() {
    presetsLocked = false;
    updatePresetButtonsDisabled(false);
}

// Обновляет визуализацию слотов пресетов, полученных с сервера
function renderPresetSlots(items) {
    const slotsById = {};
    (items || []).forEach((item) => {
        if (item && typeof item.slot === 'number') {
            slotsById[item.slot] = item;
        }
    });
    presetState = slotsById;
    for (let slot = 1; slot <= 5; slot += 1) {
        const nameEl = document.getElementById(`preset-name-${slot}`);
        const updatedEl = document.getElementById(`preset-updated-${slot}`);
        if (!nameEl) {
            continue;
        }
        const data = slotsById[slot];
        if (data) {
            const presetName = data.name || PRESET_DEFAULT_NAME;
            nameEl.textContent = presetName;
            nameEl.classList.remove('preset-slot-name--empty');
            if (updatedEl) {
                updatedEl.textContent = data.updated_at ? new Date(data.updated_at).toLocaleString() : '';
            }
        } else {
            nameEl.textContent = PRESET_DEFAULT_NAME;
            nameEl.classList.add('preset-slot-name--empty');
            if (updatedEl) {
                updatedEl.textContent = '';
            }
        }
    }
}

// Собираем текущее состояние всех контролов для сохранения пресета
function collectPresetPayload() {
    const payload = {};
    document.querySelectorAll('.controls input, .controls select, .controls textarea').forEach((field) => {
        if (!field.id || field.type === 'file') {
            return;
        }
        if (field.type === 'checkbox') {
            payload[field.id] = field.checked;
        } else {
            payload[field.id] = field.value;
        }
    });
    return payload;
}

// Применяет загруженный пресет к элементам управления
function applyPresetPayload(payload) {
    if (!payload || typeof payload !== 'object') {
        return;
    }
    Object.entries(payload).forEach(([id, value]) => {
        const field = document.getElementById(id);
        if (!field) {
            return;
        }
        if (field.type === 'checkbox') {
            field.checked = Boolean(value);
            field.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            field.value = value;
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
}

// Получает список пресетов из API и синхронизирует UI
async function refreshPresetSlots() {
    const grid = document.getElementById('presets-grid');
    if (!grid) {
        return;
    }
    try {
        const response = await fetch('/presets', { credentials: 'include' });
        if (redirectIfUnauthorized(response, 'Войдите, чтобы сохранять пресеты.')) {
            lockPresetPanel('Войдите, чтобы сохранять пресеты.');
            presetState = {};
            return;
        }
        const data = await response.json();
        renderPresetSlots(Array.isArray(data) ? data : []);
        unlockPresetPanel();
        hideAuthBanner();
        updatePresetsHint('Пресет сохранён.');
    } catch (error) {
        console.error('Не удалось сохранить пресет', error);
        showAuthBanner('Не удалось получить список пресетов.');
    }
}

// Отправляет текущие параметры на сервер для сохранения в выбранном слоте
async function savePreset(slot) {
    try {
        const payload = collectPresetPayload();
        const existing = presetState[slot];
        const defaultName = existing && existing.name && existing.name !== PRESET_DEFAULT_NAME ? existing.name : '';
        const nameInput = prompt('Название пресета', defaultName || '');
        if (nameInput === null) {
            return;
        }
        const response = await fetch(`/presets/${slot}`, {
            credentials: 'include',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: nameInput,
                payload: payload,
            }),
        });
        if (redirectIfUnauthorized(response, 'Войдите, чтобы сохранять пресеты.')) {
            lockPresetPanel('Войдите, чтобы сохранять пресеты.');
            return;
        }
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Не удалось загрузить пресет.');
        }
        updatePresetsHint('Пресет сохранен.');
        hideAuthBanner();
        await refreshPresetSlots();
    } catch (error) {
        console.error('Не удалось загрузить пресет', error);
        alert(error.message);
    }
}

// Загружает пресет из слота и перерисовывает графики
async function loadPreset(slot) {
    try {
        const response = await fetch(`/presets/${slot}`, { credentials: 'include' });
        if (redirectIfUnauthorized(response, 'Войдите, чтобы сохранять пресеты.')) {
            lockPresetPanel('Войдите, чтобы сохранять пресеты.');
            return;
        }
        if (response.status === 404) {
            alert('В этом слоте пока нет сохранённого пресета.');
            await refreshPresetSlots();
            return;
        }
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Не удалось загрузить пресет.');
        }
        const data = await response.json();
        applyPresetPayload(data.payload || {});
        updatePresetsHint(`Пресет "${data.name}" загрузен.`);
        hideAuthBanner();
        await processAndPlot();
    } catch (error) {
        console.error('Не удалось загрузить пресет', error);
        alert(error.message);
    }
}

// Удаляет пресет с бэкенда и обновляет UI
async function deletePreset(slot) {
    try {
        const response = await fetch(`/presets/${slot}`, {
            credentials: 'include',
            method: 'DELETE',
        });
        if (redirectIfUnauthorized(response, 'Войдите, чтобы управлять пресетами.')) {
            lockPresetPanel('Войдите, чтобы сохранять пресеты.');
            return;
        }
        if (response.status === 404) {
            alert('Слот уже свободен.');
            await refreshPresetSlots();
            return;
        }
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Не удалось удалить пресет.');
        }
        updatePresetsHint('Слот очищен.');
        hideAuthBanner();
        await refreshPresetSlots();
    } catch (error) {
        console.error('Не удалось удалить пресет', error);
        alert(error.message);
    }
}

// Назначает обработчики кликов для слотов пресетов
function initPresetPanel() {
    const grid = document.getElementById('presets-grid');
    if (!grid) {
        return;
    }
    grid.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button || button.disabled) {
            return;
        }
        const slot = Number(button.dataset.slot);
        if (!slot) {
            return;
        }
        const action = button.dataset.action;
        if (action === 'save') {
            savePreset(slot);
        } else if (action === 'load') {
            loadPreset(slot);
        } else if (action === 'delete') {
            deletePreset(slot);
        }
    });
    refreshPresetSlots();
}

// Инициализация drag-and-drop
function initDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('files');
    const body = document.body;
    
    // Создаем overlay для перетаскивания
    const dragOverlay = document.createElement('div');
    dragOverlay.className = 'drag-overlay';
    dragOverlay.innerHTML = '<div class="drag-overlay-text">Перетащите файлы сюда</div>';
    document.body.appendChild(dragOverlay);
    
    // Флаг для отслеживания обработки события
    let isProcessingDrop = false;
    
    // Обработчики для области перетаскивания
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('drag-over');
        dragOverlay.classList.add('visible');
    });
    
    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const rect = dropZone.getBoundingClientRect();
        if (
            e.clientX < rect.left || 
            e.clientX > rect.right || 
            e.clientY < rect.top || 
            e.clientY > rect.bottom
        ) {
            dropZone.classList.remove('drag-over');
            dragOverlay.classList.remove('visible');
        }
    });
    
    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-over');
        dragOverlay.classList.remove('visible');
        
        // Проверяем, не обрабатывается ли уже событие
        if (isProcessingDrop) return;
        isProcessingDrop = true;
        
        const files = e.dataTransfer.files;
        if (files.length) {
            // Автоматически загружаем файлы при перетаскивании
            handleDroppedFiles(files);
            //addMoreFiles(); // Автоматическая загрузка
        }
        
        // Сбрасываем флаг после обработки
        setTimeout(() => { isProcessingDrop = false; }, 100);
    });
    // Обработчики для всего документа
    document.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        // Показываем оверлей только если не над dropZone
        if (!e.target.closest('#dropZone')) {
            dragOverlay.classList.add('visible');
        }
    });
    
    document.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        // Проверяем, покинули ли мы документ
        if (
            e.clientX <= 0 || 
            e.clientY <= 0 || 
            e.clientX >= window.innerWidth || 
            e.clientY >= window.innerHeight
        ) {
            dragOverlay.classList.remove('visible');
        }
    });
    
    document.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragOverlay.classList.remove('visible');
        
        // Проверяем, не обрабатывается ли уже событие
        if (isProcessingDrop) return;
        isProcessingDrop = true;
        
        // Если файлы были сброшены не на dropZone, обрабатываем их
        if (!e.target.closest('#dropZone')) {
            const files = e.dataTransfer.files;
            if (files.length) {
                handleDroppedFiles(files);
                //addMoreFiles(); // Автоматическая загрузка
            }
        }
        
        // Сбрасываем флаг после обработки
        setTimeout(() => { isProcessingDrop = false; }, 100);
    });
    
    // Обработчик изменения input
    fileInput.addEventListener('change', function() {
        if (this.files.length) {
            handleDroppedFiles(this.files);
            addMoreFiles(); // Автоматическая загрузка
            this.value = ''; // Сброс значения
        }
    });
    
    const dropZoneButton = document.querySelector('#dropZone button');
    if (dropZoneButton) {
        dropZoneButton.addEventListener('click', function(e) {
// Включает удаление спектра по клику на линию графика
            e.stopPropagation();
            fileInput.click();
        });
    }
}

// Обработка сброшенных файлов
function handleDroppedFiles(files) {
    draggedFiles = Array.from(files);
    updateFileList();
}
// Новая функция для обновления списка файлов
// Обновление списка файлов
function updateFileList() {
    const fileCount = document.getElementById('file-count');
    fileCount.textContent = `Выбрано файлов: ${draggedFiles.length}`;
    
    const fileListContainer = document.createElement('div');
    fileListContainer.className = 'file-list';
    
    const oldList = document.querySelector('.file-list');
    if (oldList) {
        oldList.remove();
    }
    
    draggedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span class="file-icon">📄</span>
            <span class="file-name">${file.name}</span>
            <span class="file-remove" data-index="${index}">✕</span>
        `;
        fileListContainer.appendChild(fileItem);
    });
    
    const fileCountElement = document.getElementById('file-count');
    fileCountElement.parentNode.insertBefore(fileListContainer, fileCountElement.nextSibling);
    
    // Обработчики для кнопок удаления
    document.querySelectorAll('.file-remove').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const index = parseInt(this.getAttribute('data-index'));
            removeFileFromList(index);
        });
    });
}

// Новая функция для удаления файла
function removeFileFromList(index) {
    if (index >= 0 && index < draggedFiles.length) {
        // Удаляем файл из массива
        const removedFileName = draggedFiles[index].name;
        draggedFiles.splice(index, 1);
        
        // Обновляем отображение списка файлов
        updateFileList();
        
        // Если файл был уже загружен, удаляем его из данных
        const fileIndex = fileNames.indexOf(removedFileName);
        if (fileIndex !== -1) {
            allFrequencies.splice(fileIndex, 1);
            allAmplitudes.splice(fileIndex, 1);
            fileNames.splice(fileIndex, 1);
            
            // Перестраиваем график
            rebuildPlot();
            peakTableData = null;
            updatePeakTableVisibility();
            
            // Обновляем список загруженных файлов
            updateUploadedFilesList();
        }
    }
}














document.addEventListener('DOMContentLoaded', function() {
    initDragAndDrop();
    console.log('DOM loaded');
    console.log('Files input:', document.getElementById('files'));
    console.log('Plot element:', document.getElementById('spectrum_plot'));
});

// Сокращает длинные имена файлов для легенды
function truncateFileName(name, length = 20) {
    if (!name) return `Файл`;
    return name.length > length ? name.slice(0, length - 3) + '...' : name;
}

function plotCombinedSpectrum(allFrequencies, allAmplitudes, fileNames, allPeaks, mean_amplitude, std_amplitude, showOnlyMeanStd, boxplotStats, title, movingAverages = []) {
    const plotData = [];
    const lineColors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b'];

    
    // Линейные графики для каждого файла
    if (!showOnlyMeanStd) {
        for (let i = 0; i < allFrequencies.length; i++) {
            plotData.push({
                x: allFrequencies[i],
                y: allAmplitudes[i],
                type: 'scatter',
                mode: 'lines',
                name: truncateFileName(fileNames[i]) || `Файл ${i + 1}`,
                line: { 
                    color: lineColors[i % lineColors.length],
                    width: 1
                },
                yaxis: 'y1',
                // Добавляем кастомные данные для идентификации
                customdata: [i],
                meta: {
                    fileIndex: i,
                    role: 'spectrum',
                    baseOpacity: 1,
                    lineWidth: 1
                }
            });
        
            if (allPeaks[i] && allPeaks[i].length > 0) {
                const peakX = allPeaks[i].map(index => allFrequencies[i][index]);
                const peakY = allPeaks[i].map(index => allAmplitudes[i][index]);

                plotData.push({
                    x: peakX,
                    y: peakY,
                    type: 'scatter',
                    mode: 'markers+text',
                    name: `Пики ${truncateFileName(fileNames[i]) || `Файл ${i + 1}`}`,
                    marker: { color: lineColors[i % lineColors.length], size: 8, symbol: 'circle-open' },
                    text: peakX.map(coord => coord.toFixed(2)),
                    textposition: 'top center',
                    textfont: {
                        size: 10,
                        color: lineColors[i % lineColors.length]
                    },
                    yaxis: 'y1',
                    meta: {
                        fileIndex: i,
                        role: 'peaks',
                        baseOpacity: 1
                    }
                });
            }

            // Скользящая средняя (если есть)
            if (movingAverages && movingAverages[i] && movingAverages[i].length > 0) {
                plotData.push({
                    x: allFrequencies[i],
                    y: movingAverages[i],
                    type: 'scatter',
                    mode: 'lines',
                    name: `Ср. ${truncateFileName(fileNames[i])}`,
                    line: { 
                        color: lineColors[i % lineColors.length],
                        width: 2,
                        dash: 'dash'
                    },
                    opacity: 0.8,
                    yaxis: 'y1',
                    meta: {
                        fileIndex: i,
                        role: 'moving-average',
                        baseOpacity: 0.8,
                        lineWidth: 2
                    }
                });
            }
        }

    
    }

    // Среднее значение и стандартное отклонение
    if (mean_amplitude && mean_amplitude.length > 0 && std_amplitude && std_amplitude.length > 0) {
        plotData.push(
            {
                x: allFrequencies[0],
                y: mean_amplitude,
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее значение',
                line: { color: 'red', width: 3 },
                yaxis: 'y1',
                meta: {
                    role: 'mean',
                    baseOpacity: 1,
                    lineWidth: 3
                }
            },
            {
                x: allFrequencies[0],
                y: mean_amplitude.map((m, idx) => m + std_amplitude[idx]),
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее + 1σ',
                line: { color: 'orange', width: 2, dash: 'dot' },
                yaxis: 'y1',
                meta: {
                    role: 'mean-plus-sigma',
                    baseOpacity: 1,
                    lineWidth: 2
                }
            },
            {
                x: allFrequencies[0],
                y: mean_amplitude.map((m, idx) => m - std_amplitude[idx]),
                type: 'scatter',
                mode: 'lines',
                name: 'Среднее - 1σ',
                line: { color: 'orange', width: 2, dash: 'dot' },
                yaxis: 'y1',
                meta: {
                    role: 'mean-minus-sigma',
                    baseOpacity: 1,
                    lineWidth: 2
                }
            }
        );
    }

    // Box plots
    if (boxplotStats && boxplotStats.length > 0) {
        const positions = [];
        const step = (allFrequencies[0][allFrequencies[0].length - 1] - allFrequencies[0][0]) / (allFrequencies.length + 1);

        for (let idx = 0; idx < allFrequencies.length; idx++) {
            positions.push(allFrequencies[0][0] + (idx + 1) * step);
        }

        plotData.push({
            y: allAmplitudes.flat(),
            x: positions.flatMap((pos, idx) => Array(allAmplitudes[idx].length).fill(pos)),
            type: 'box',
            name: 'Распределение',
            boxpoints: 'all',
            jitter: 0.5,
            pointpos: 0,
            marker: { size: 3, opacity: 0.5 },
            line: { width: 1 },
            fillcolor: 'rgba(100, 100, 255, 0.3)',
            yaxis: 'y1',
            hoverinfo: 'y+name',
            showlegend: false,
            meta: {
                role: 'boxplot',
                baseOpacity: 1
            }
        });
    }

    const layout = {
        title: title.includes('(') ? title : title + ` (${allFrequencies.length} файлов)`,
        xaxis: { title: 'Волновое число (см⁻¹)' },
        yaxis: { title: 'Интенсивность (Отн. ед.)' },
        plot_bgcolor: document.body.classList.contains('dark-theme') ? '#1e1e1e' : '#ffffff',
        paper_bgcolor: document.body.classList.contains('dark-theme') ? '#1e1e1e' : '#ffffff',
        font: { color: document.body.classList.contains('dark-theme') ? '#e0e0e0' : '#222' },
        showlegend: true,
        legend: {
            orientation: 'v',
            y: 1,
            x: 1.02,
            yanchor: 'top',
            xanchor: 'left'
        },
        margin: { l: 60, r: 150, b: 60, t: 80, pad: 4 }
    };

    Plotly.newPlot('spectrum_plot', plotData, layout, { responsive: true }).then(function() {
        initLegendHover();
    });
}

async function uploadFiles() {
    if (draggedFiles.length === 0) {
        alert('Пожалуйста, выберите файлы для загрузки');
        return;
    }

    const formData = new FormData();
    for (let file of draggedFiles) {
        formData.append('files', file);
    }

    try {
        const response = await fetch('/upload_files', {
            credentials: 'include',
            method: 'POST',
            body: formData,
        });

        if (redirectIfUnauthorized(response)) {
            return;
        }

        if (!response.ok) {
            throw new Error(`Ошибка сервера: ${response.status}`);
        }

        const result = await response.json();

        if (result.frequencies && result.amplitudes) {
            // Заменяем данные полностью
            allFrequencies = result.frequencies.map(arr => arr.map(Number));
            allAmplitudes = result.amplitudes.map(arr => arr.map(Number));
            fileNames = result.files;

            // Обновляем график
            rebuildPlot();
            
            // Обновляем список загруженных файлов
            updateUploadedFilesList();

            peakTableData = null;
            updatePeakTableVisibility();

            // Очищаем список перетащенных файлов после успешной загрузки
            draggedFiles = [];
            document.getElementById('file-count').textContent = `Загружено ${result.files.length} файлов`;
            
            // Удаляем список файлов
            const fileList = document.querySelector('.file-list');
            if (fileList) {
                fileList.remove();
            }
        } else {
            throw new Error(result.error || 'Неизвестная ошибка при загрузке');
        }
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        alert('Ошибка: ' + error.message);
    }
}

// Обновление списка загруженных файлов
function updateUploadedFilesList() {
    const uploadedFilesContainer = document.getElementById('uploaded-files-container');
    if (!uploadedFilesContainer) return;
    
    uploadedFilesContainer.innerHTML = '';
    
    if (fileNames.length === 0) {
        uploadedFilesContainer.innerHTML = '<div class="no-files">Нет загруженных файлов</div>';
        return;
    }
    
    fileNames.forEach((fileName, index) => {
        const fileElement = document.createElement('div');
        fileElement.classList.add('uploaded-file');
        fileElement.innerHTML = `
            <span class="file-icon">📄</span>
            <span class="file-name" data-index="${index}">${fileName}</span>
            <span class="file-remove" data-index="${index}">✕</span>
        `;
        uploadedFilesContainer.appendChild(fileElement);
        
        // Добавляем обработчики для подсветки спектра
        fileElement.addEventListener('mouseenter', () => {
            highlightSpectrum(index);
        });
        fileElement.addEventListener('mouseleave', () => {
            resetSpectrumHighlight();
        });
    });
    
    // Обработчики для кнопок удаления загруженных файлов
    document.querySelectorAll('#uploaded-files-container .file-remove').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const index = parseInt(this.getAttribute('data-index'));
            removeUploadedFile(index);
        });
    });
}

// Удаление загруженного файла
function removeUploadedFile(index) {
    if (index >= 0 && index < fileNames.length) {
        // Удаляем файл из массивов
        allFrequencies.splice(index, 1);
        allAmplitudes.splice(index, 1);
        fileNames.splice(index, 1);
        
        // Перестраиваем график
        rebuildPlot();
        peakTableData = null;
        updatePeakTableVisibility();
        
        // Обновляем список загруженных файлов
        updateUploadedFilesList();
    }
}

// Перестраиваем график
function rebuildPlot() {
    if (allFrequencies.length === 0) {
        // Если файлов нет, очищаем график
        Plotly.purge('spectrum_plot');
        document.getElementById('spectrum_plot').innerHTML = '';
        return;
    }
    
    plotCombinedSpectrum(
        allFrequencies,
        allAmplitudes,
        fileNames,
        [],
        [],
        [],
        false,
        [],
        `Спектры (${allFrequencies.length} файлов)`
    );
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    initDragAndDrop();
    updateUploadedFilesList();
});

// Основной цикл обработки: отправляем параметры на бэкенд и обновляем визуализацию
async function processAndPlot() {
    console.log("Обработка данных...");

    if (allFrequencies.length === 0 || allAmplitudes.length === 0) {
        alert("Данные не загружены. Сначала загрузите файлы.");
        return;
    }

    try {
        const getNumberValue = (id, defaultValue) => {
            const val = document.getElementById(id).value;
            return val === '' ? defaultValue : Number(val);
        };

        const params = {
            frequencies: allFrequencies,
            amplitudes: allAmplitudes,
            remove_baseline: document.getElementById('remove_baseline').checked,
            apply_smoothing: document.getElementById('apply_smoothing').checked,
            normalize: document.getElementById('normalize').checked,
            find_peaks: document.getElementById('find_peaks').checked,
            calculate_mean_std: document.getElementById('calculate_mean_std').checked,
            calculate_boxplot: document.getElementById('calculate_boxplot').checked,
            lam: getNumberValue('lam', 1000),
            p: getNumberValue('p', 0.001),
            window_length: getNumberValue('window_length', 25),
            polyorder: getNumberValue('polyorder', 2),
            width: getNumberValue('peak_width', 1),
            prominence: getNumberValue('peak_prominence', 1),
            min_freq: getNumberValue('min_freq', 0),
            max_freq: getNumberValue('max_freq', 10000),
            show_moving_average: document.getElementById('show_moving_average').checked,
            moving_average_window: getNumberValue('moving_average_window', 10)
        };

        const response = await fetch('/process_data', {
            credentials: 'include',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });

        if (redirectIfUnauthorized(response)) {
            return;
        }

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Ошибка сервера: ${response.status} ${errorText}`);
        }

        const result = await response.json();

        processedData = {
            frequencies: result.frequencies,
            amplitudes: result.processed_amplitudes,
            fileNames: fileNames, // Используем текущие fileNames
            params: params
        };

        const peaksInfo = Array.isArray(result.peaks_info) ? result.peaks_info : [];

        if (Array.isArray(result.peaks) || hasAnyPeakInfo(peaksInfo)) {
            // Кэшируем подготовленные данные по пикам, чтобы переиспользовать их при переключении чекбоксов
            peakTableData = {
                frequencies: result.frequencies,
                amplitudes: result.processed_amplitudes,
                peaks: Array.isArray(result.peaks) ? result.peaks : [],
                peaksInfo,
                fileNames: [...fileNames]
            };
        } else {
            peakTableData = null;
        }

        plotCombinedSpectrum(
            result.frequencies,
            result.processed_amplitudes,
            fileNames, // Используем текущие fileNames
            result.peaks || [],
            result.mean_amplitude || [],
            result.std_amplitude || [],
            document.getElementById('show_only_mean_std').checked,
            result.boxplot_stats || [],
            "Обработанные спектры (" + result.frequencies.length + " файлов)",
            result.moving_averages || []
        );
        
        window.latestMeanAmplitude = result.mean_amplitude;
        updatePeakTableVisibility();

    } catch (error) {
        console.error("Ошибка:", error);
        alert("Ошибка обработки: " + error.message);
    }
}

// Формирует архив с обработанными спектрами и инициирует скачивание
async function downloadProcessedData() {
    if (processedData.frequencies.length === 0) {
        alert("Нет обработанных данных для сохранения. Сначала обработайте файлы.");
        return;
    }

    try {
        const response = await fetch('/export_processed_data', {
            credentials: 'include',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(processedData),
        });

        if (redirectIfUnauthorized(response, 'Войдите, чтобы выгружать данные.')) {
            return;
        }

        if (!response.ok) throw new Error('Ошибка экспорта');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'processed_spectra.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch (error) {
        console.error("Ошибка экспорта:", error);
        alert("Ошибка экспорта: " + error.message);
    }
}

// Экспортирует усреднённый спектр в CSV
async function downloadMeanSpectrum() {
    if (!allFrequencies.length || !window.latestMeanAmplitude) {
        alert("Сначала загрузите и обработайте данные.");
        return;
    }

    const params = {
        remove_baseline: document.getElementById('remove_baseline').checked,
        lam: document.getElementById('lam').value || "1000",
        p: document.getElementById('p').value || "0.001",
        apply_smoothing: document.getElementById('apply_smoothing').checked,
        window_length: document.getElementById('window_length').value || "25",
        polyorder: document.getElementById('polyorder').value || "1",
        normalize: document.getElementById('normalize').checked,
        find_peaks: document.getElementById('find_peaks').checked,
        peak_width: document.getElementById('peak_width').value || "1",
        peak_prominence: document.getElementById('peak_prominence').value || "1",
        calculate_mean_std: document.getElementById('calculate_mean_std').checked,
        calculate_boxplot: document.getElementById('calculate_boxplot').checked,
        min_freq: document.getElementById('min_freq').value || "0",
        max_freq: document.getElementById('max_freq').value || "10000"
    };

    try {
        const exportParams = {
            frequencies: allFrequencies[0],
            mean_amplitude: window.latestMeanAmplitude,
            params: params
        };

        const response = await fetch('/export_mean_spectrum', {
            credentials: 'include',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(exportParams),
        });

        if (redirectIfUnauthorized(response, 'Войдите, чтобы выгружать данные.')) {
            return;
        }

        if (!response.ok) throw new Error('Ошибка экспорта');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'mean_spectrum.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();

    } catch (error) {
        console.error("Ошибка экспорта:", error);
        alert("Ошибка экспорта: " + error.message);
    }
}

// Строим таблицу пиков: каждая группа оборачивается в <details> для компактности
function renderPeakTable(peaksInfoList, fileNames) {
    const container = document.getElementById('peak_table_container');
    container.innerHTML = '';

    peaksInfoList.forEach((datasetPeaks, index) => {
        if (!datasetPeaks || datasetPeaks.length === 0) {
            return;
        }

        const group = document.createElement('details');
        group.className = 'peak-table-group';
        if (index === 0) {
            group.open = true;
        }

        const summary = document.createElement('summary');
        summary.className = 'peak-table-group__summary';
        summary.textContent = fileNames[index] ? `Пики — ${fileNames[index]}` : `Пики — Файл ${index + 1}`;
        group.appendChild(summary);

        const tableWrapper = document.createElement('div');
        tableWrapper.className = 'peak-table-group__table-wrapper';

        const table = document.createElement('table');
        table.className = 'peak-table';

        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        ['#', 'Частота (см⁻¹)', 'Интенсивность'].forEach((text, colIndex) => {
            const th = document.createElement('th');
            th.textContent = text;
            th.className = 'peak-table__head-cell';
            if (colIndex > 0) {
                th.classList.add('peak-table__head-cell--numeric');
            }
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');

        datasetPeaks.forEach((peakInfo, peakIndex) => {
            const row = document.createElement('tr');
            row.className = 'peak-table__row';

            const freq = Number(peakInfo.frequency);
            const amp = Number(peakInfo.amplitude);
            const order = Number.isFinite(Number(peakInfo.order)) ? Number(peakInfo.order) : peakIndex + 1;

            [order, freq.toFixed(2), amp.toFixed(2)].forEach((val, colIndex) => {
                const td = document.createElement('td');
                td.textContent = val;
                td.className = 'peak-table__cell';
                if (colIndex === 0) {
                    td.classList.add('peak-table__cell--index');
                } else {
                    td.classList.add('peak-table__cell--numeric');
                }
                row.appendChild(td);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        tableWrapper.appendChild(table);
        group.appendChild(tableWrapper);
        container.appendChild(group);
    });
}

// Проверяет, содержит ли хотя бы один набор информацию о пиках
function hasAnyPeakInfo(peaksInfoList) {
    if (!Array.isArray(peaksInfoList)) {
        return false;
    }
    return peaksInfoList.some((entry) => Array.isArray(entry) && entry.length > 0);
}

// Управляем отображением панели пиков в зависимости от настроек и наличия данных
function updatePeakTableVisibility() {
    const container = document.getElementById('peak_table_container');
    if (!container) {
        return;
    }

    container.classList.remove('peaks-panel--visible', 'peaks-panel--empty');
    container.innerHTML = '';

    const showTableCheckbox = document.getElementById('show_peak_table');
    if (!showTableCheckbox || !showTableCheckbox.checked) {
        return;
    }

    const peaksInfo = Array.isArray(peakTableData && peakTableData.peaksInfo) ? peakTableData.peaksInfo : [];

    if (!peakTableData || peaksInfo.length === 0 || !hasAnyPeakInfo(peaksInfo)) {
        container.classList.add('peaks-panel--visible', 'peaks-panel--empty');
        const placeholder = document.createElement('div');
        placeholder.className = 'no-peaks';
        placeholder.textContent = 'Пики не найдены или не рассчитаны.';
        container.appendChild(placeholder);
        return;
    }

    container.classList.add('peaks-panel--visible');

    renderPeakTable(
        peaksInfo,
        peakTableData.fileNames
    );
}





// Усиливает выбранную линию и приглушает остальные кривые
function highlightSingleSpectrum(curveNumber) {
    // Получаем информацию о всех кривых
    Plotly.restyle('spectrum_plot', {
        'line.width': Array(100).fill(1) // Сначала сбрасываем все
    }).then(function() {
        // Затем выделяем только одну нужную кривую
        Plotly.restyle('spectrum_plot', {
            'line.width': 4
        }, [curveNumber]);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            document.body.classList.toggle('dark-theme');
        });
    }
});

// Добавьте эту функцию в app.js
// Настраивает подсказки для элементов справки
function initTooltips() {
    const helpIcons = document.querySelectorAll('.help-icon');
    
    helpIcons.forEach(icon => {
        // Следим за движением мыши над иконкой
        icon.addEventListener('mousemove', function(e) {
            const tooltip = this.querySelector('::after') || this;
            const tooltipText = this.getAttribute('data-tooltip');
            
            if (tooltipText) {
                // Позиционируем подсказку рядом с курсором
                const x = e.clientX + 15;
                const y = e.clientY + 15;
                
                // Создаем или обновляем стиль подсказки
                let style = document.getElementById('tooltip-style');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'tooltip-style';
                    document.head.appendChild(style);
                }
                
                style.textContent = `
                    .help-icon:hover::after {
                        left: ${x}px !important;
                        top: ${y}px !important;
                        transform: none !important;
                    }
                `;
            }
        });
        
        // При уходе с иконки убираем подсказку
        icon.addEventListener('mouseleave', function() {
            const style = document.getElementById('tooltip-style');
            if (style) {
                style.remove();
            }
        });
    });
}


document.addEventListener('DOMContentLoaded', function() {
    initTooltips();
});


document.addEventListener('DOMContentLoaded', function() {
    const showPeakTableCheckbox = document.getElementById('show_peak_table');
    if (showPeakTableCheckbox) {
        showPeakTableCheckbox.addEventListener('change', updatePeakTableVisibility);
    }

    const findPeaksCheckbox = document.getElementById('find_peaks');
    if (findPeaksCheckbox) {
        findPeaksCheckbox.addEventListener('change', function() {
            if (!findPeaksCheckbox.checked) {
                const showCheckbox = document.getElementById('show_peak_table');
                if (showCheckbox) {
                    showCheckbox.checked = false;
                }
                peakTableData = null;
            }
            updatePeakTableVisibility();
        });
    }
});



// Добавьте эту функцию для обработки кликов по линиям графика
function initGraphClickHandler() {
    const plotElement = document.getElementById('spectrum_plot');
    
    plotElement.on('plotly_click', function(data) {
        if (data.points && data.points[0]) {
            const point = data.points[0];
            const traceName = point.data.name || '';
            
            // Игнорируем неспектральные элементы
            if (traceName.includes('Пики') || 
                traceName.includes('Среднее') ||
                traceName.includes('СКО') ||
                traceName.includes('Ср.') ||
                traceName.includes('+') ||
                traceName.includes('-')) {
                return;
            }
            
            // Находим индекс спектра
            const spectrumIndex = findSpectrumIndexByName(traceName);
            if (spectrumIndex !== -1) {
                showDeleteButton(data.event.clientX, data.event.clientY, spectrumIndex);
            }
        }
    });
}


// Добавьте переменную для хранения выбранного спектра
let selectedSpectrumIndex = -1;


// Создаёт кнопку удаления спектра, если её ещё нет
function createDeleteButton() {
    if (!document.getElementById('delete-spectrum-btn')) {
        const deleteBtn = document.createElement('button');
        deleteBtn.id = 'delete-spectrum-btn';
        deleteBtn.className = 'delete-spectrum-btn';
        deleteBtn.textContent = 'Удалить';
        deleteBtn.onclick = removeSelectedSpectrum;
        document.body.appendChild(deleteBtn);
    }
    return document.getElementById('delete-spectrum-btn');
}

// Добавьте функцию для показа кнопки удаления
// Располагает кнопку удаления рядом с точкой клика
function showDeleteButton(x, y, spectrumIndex) {
    const deleteBtn = createDeleteButton();
    selectedSpectrumIndex = spectrumIndex;
    
    deleteBtn.style.left = (x + 10) + 'px';
    deleteBtn.style.top = (y + 10) + 'px';
    deleteBtn.style.display = 'block';
    
    // Скрываем кнопку через 3 секунды или при клике вне её
    setTimeout(() => {
        if (deleteBtn.style.display === 'block') {
            deleteBtn.style.display = 'none';
        }
    }, 3000);
}

// Функция удаления спектра
// Удаляет выбранный спектр и обновляет графики
function removeSelectedSpectrum() {
    if (selectedSpectrumIndex === -1) return;
    
    // Скрываем кнопку
    const deleteBtn = document.getElementById('delete-spectrum-btn');
    if (deleteBtn) deleteBtn.style.display = 'none';
    
    // Удаляем спектр
    allFrequencies.splice(selectedSpectrumIndex, 1);
    allAmplitudes.splice(selectedSpectrumIndex, 1);
    fileNames.splice(selectedSpectrumIndex, 1);
    
    // Перестраиваем график
    rebuildPlot();
    peakTableData = null;
    updatePeakTableVisibility();
    selectedSpectrumIndex = -1;
}


// Функция для поиска индекса спектра по имени
// Находит позицию спектра в массиве по названию серии Plotly
function findSpectrumIndexByName(traceName) {
    for (let i = 0; i < fileNames.length; i++) {
        const fileName = truncateFileName(fileNames[i]) || `Файл ${i + 1}`;
        if (traceName === fileName || traceName === `Ср. ${fileName}`) {
            return i;
        }
    }
    return -1;
}

// Добавьте вызов createDeleteButton при загрузке
document.addEventListener('DOMContentLoaded', function() {
    createDeleteButton();
});


// Добавляет новые файлы, не очищая ранее загруженные
async function addMoreFiles() {
    if (draggedFiles.length === 0) {
        return;
    }

    const formData = new FormData();
    for (let file of draggedFiles) {
        formData.append('files', file);
    }

    try {
        const response = await fetch('/upload_files', {
            credentials: 'include',
            method: 'POST',
            body: formData,
        });

        if (redirectIfUnauthorized(response)) {
            return;
        }

        if (!response.ok) {
            throw new Error(`Ошибка сервера: ${response.status}`);
        }

        const result = await response.json();

        if (result.frequencies && result.amplitudes) {
            // Добавляем новые данные к существующим
            const newFrequencies = result.frequencies.map(arr => arr.map(Number));
            const newAmplitudes = result.amplitudes.map(arr => arr.map(Number));
            const newFileNames = result.files;

            allFrequencies = [...allFrequencies, ...newFrequencies];
            allAmplitudes = [...allAmplitudes, ...newAmplitudes];
            fileNames = [...fileNames, ...newFileNames];

            // Обновляем график <- ДОБАВЬТЕ ЭТУ СТРОЧКУ
            rebuildPlot();
            
            // Обновляем список загруженных файлов
            updateUploadedFilesList();

            peakTableData = null;
            updatePeakTableVisibility();

            // Очищаем список перетащенных файлов после успешной загрузки
            draggedFiles = [];
            document.getElementById('file-count').textContent = `Всего файлов: ${fileNames.length}`;
            
            // Удаляем список файлов
            const fileList = document.querySelector('.file-list');
            if (fileList) {
                fileList.remove();
            }
        } else {
            throw new Error(result.error || 'Неизвестная ошибка при загрузке');
        }
    } catch (error) {
        console.error('Ошибка добавления файлов:', error);
        alert('Ошибка: ' + error.message);
    }
}

// Функция для очистки всех спектров
// Полностью сбрасывает состояние приложения и графики
function clearAllSpectra() {
    if (allFrequencies.length === 0) {
        alert('Нет спектров для очистки');
        return;
    }
    
    if (confirm(`Очистить все ${allFrequencies.length} спектров?`)) {
        // Очищаем все массивы данных
        allFrequencies = [];
        allAmplitudes = [];
        fileNames = [];
        processedData = {
            frequencies: [],
            amplitudes: [],
            fileNames: [],
            params: {}
        };
        draggedFiles = [];
        peakTableData = null;
        updatePeakTableVisibility();
        
        // Очищаем график
        Plotly.purge('spectrum_plot');
        document.getElementById('spectrum_plot').innerHTML = '';
        
        // Очищаем список загруженных файлов
        const uploadedFilesContainer = document.getElementById('uploaded-files-container');
        if (uploadedFilesContainer) {
            uploadedFilesContainer.innerHTML = '<div class="no-files">Нет загруженных файлов</div>';
        }
        
        // Очищаем список выбранных файлов
        const fileList = document.querySelector('.file-list');
        if (fileList) {
            fileList.remove();
        }
        
        // Обновляем счетчик файлов
        document.getElementById('file-count').textContent = 'Выбрано файлов: 0';
        
        alert('Все спектры очищены');
    }
}




























// Запрашивает у AI сервиса текстовое объяснение спектра
async function analyzeWithAI() {
    if (allFrequencies.length === 0) {
        alert("Сначала загрузите и обработайте данные.");
        return;
    }

    try {
        // Используем средний спектр или первый доступный
        const frequencies = processedData.frequencies.length > 0 ? 
            processedData.frequencies[0] : allFrequencies[0];
        const amplitudes = processedData.amplitudes.length > 0 ? 
            processedData.amplitudes[0] : allAmplitudes[0];

        // Собираем параметры обработки
        const processingParams = {
            remove_baseline: document.getElementById('remove_baseline').checked,
            apply_smoothing: document.getElementById('apply_smoothing').checked,
            normalize: document.getElementById('normalize').checked,
            min_freq: document.getElementById('min_freq').value || 0,
            max_freq: document.getElementById('max_freq').value || 10000,
            lam: document.getElementById('lam').value || 1000,
            p: document.getElementById('p').value || 0.001,
            window_length: document.getElementById('window_length').value || 25,
            polyorder: document.getElementById('polyorder').value || 1
        };

        const response = await fetch('/analyze_spectrum', {
            credentials: 'include',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frequencies: frequencies,
                amplitudes: amplitudes,
                processing_params: processingParams
            }),
        });

        const result = await response.json();

        if (result.success) {
            // Показываем результат анализа
            showAIAnalysis(result.analysis);
        } else {
            alert("Ошибка анализа: " + result.analysis);
        }
    } catch (error) {
        console.error("Ошибка:", error);
        alert("Ошибка при анализе: " + error.message);
    }
}

// Показывает результат AI-анализа в модальном окне
function showAIAnalysis(analysisText) {
    // Создаем модальное окно для отображения анализа
    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.top = '50%';
    modal.style.left = '50%';
    modal.style.transform = 'translate(-50%, -50%)';
    modal.style.backgroundColor = 'white';
    modal.style.padding = '20px';
    modal.style.borderRadius = '8px';
    modal.style.boxShadow = '0 4px 20px rgba(0,0,0,0.2)';
    modal.style.zIndex = '1000';
    modal.style.maxWidth = '80%';
    modal.style.maxHeight = '80%';
    modal.style.overflow = 'auto';
    modal.style.color = '#2d3748';

    // Добавляем содержимое
    modal.innerHTML = `
        <h2>Анализ DeepSeek AI</h2>
        <div style="margin: 15px 0; white-space: pre-wrap; max-height: 60vh; overflow-y: auto;">${analysisText}</div>
        <div style="text-align: center;">
            <button onclick="this.parentElement.parentElement.remove()" style="padding: 8px 16px; background: #f56565; color: white; border: none; border-radius: 4px; cursor: pointer;">
                Закрыть
            </button>
        </div>
    `;

    document.body.appendChild(modal);
}





// Подсвечивает соответствующий спектр на графике
function highlightSpectrum(fileIndex) {
    const plot = document.getElementById('spectrum_plot');
    if (!plot || !plot.data || fileIndex < 0) {
        return;
    }

    const highlightIndices = [];
    const highlightOpacities = [];
    const highlightLineIndices = [];
    const highlightLineWidths = [];

    const dimIndices = [];
    const dimOpacities = [];
    const dimLineIndices = [];
    const dimLineWidths = [];

    plot.data.forEach((trace, idx) => {
        const meta = trace.meta || {};
        if (meta.fileIndex === fileIndex) {
            highlightIndices.push(idx);
            highlightOpacities.push(meta.baseOpacity ?? 1);
            if (trace.mode && trace.mode.includes('lines')) {
                const baseWidth = meta.lineWidth ?? (trace.line && trace.line.width) ?? 1;
                highlightLineIndices.push(idx);
                highlightLineWidths.push(baseWidth + 2);
            }
        } else if (typeof meta.fileIndex === 'number') {
            dimIndices.push(idx);
            const baseOpacity = meta.baseOpacity ?? 1;
            dimOpacities.push(Math.max(0, Math.min(1, baseOpacity * 0.25)));
            if (trace.mode && trace.mode.includes('lines')) {
                const baseWidth = meta.lineWidth ?? (trace.line && trace.line.width) ?? 1;
                dimLineIndices.push(idx);
                dimLineWidths.push(Math.max(1, baseWidth * 0.75));
            }
        }
    });

    if (!highlightIndices.length) {
        return;
    }

    if (dimIndices.length) {
        Plotly.restyle(plot, { opacity: dimOpacities }, dimIndices);
    }
    if (dimLineIndices.length) {
        Plotly.restyle(plot, { 'line.width': dimLineWidths }, dimLineIndices);
    }

    Plotly.restyle(plot, { opacity: highlightOpacities }, highlightIndices);
    if (highlightLineIndices.length) {
        Plotly.restyle(plot, { 'line.width': highlightLineWidths }, highlightLineIndices);
    }
}

// Сбрасывает подсветку и возвращает исходные параметры отображения
function resetSpectrumHighlight() {
    const plot = document.getElementById('spectrum_plot');
    if (!plot || !plot.data) {
        return;
    }

    const opacityIndices = [];
    const opacities = [];
    const lineIndices = [];
    const lineWidths = [];

    plot.data.forEach((trace, idx) => {
        const meta = trace.meta || {};
        if (typeof meta.baseOpacity !== 'undefined' || typeof meta.fileIndex === 'number') {
            opacityIndices.push(idx);
            opacities.push(meta.baseOpacity ?? 1);
        }
        if (trace.mode && trace.mode.includes('lines')) {
            const baseWidth = meta.lineWidth ?? (trace.line && trace.line.width) ?? 1;
            lineIndices.push(idx);
            lineWidths.push(baseWidth);
        }
    });

    if (opacityIndices.length) {
        Plotly.restyle(plot, { opacity: opacities }, opacityIndices);
    }
    if (lineIndices.length) {
        Plotly.restyle(plot, { 'line.width': lineWidths }, lineIndices);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    initPresetPanel();
});