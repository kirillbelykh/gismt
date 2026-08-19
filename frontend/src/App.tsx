import { useState, useEffect, useRef, useCallback } from 'react';
import { Scanner } from '@yudiel/react-qr-scanner';
import './App.css';

const STORAGE_KEY = 'scanned_datamatrix_codes';
const STORAGE_TARGET_KEY = 'scanner_target_count';
const STORAGE_SSCC_LIST_KEY = 'sscc_list';
const API_BASE_URL = '/api/v1';

// Типы для TypeScript
interface OrderInfo {
  order_id: number;
  order_name?: string;
  external_order_id: string | null;
  product_name: string;
  gtin: string;
  quantity: number;
  codes: string[];
}

interface ScanResponse {
  orders: OrderInfo[];
  total_codes: number;
  found_codes: number;
  not_found_codes: string[];
}

interface AggregationResponse {
  success: boolean;
  box_id: number;
  sscc_code: string;
  order_id: number;
  total_codes_scanned: number;
  found_codes: number;
  not_found_codes: string[];
  warning?: string;
  print_status?: string;
  message?: string;
}

// Интерфейс для SSCC записи
interface SsccRecord {
  id: number;
  code: string;
  box_id: number;
  order_id: number;
  timestamp: string;
  total_codes: number;
}

function App() {
  const [codes, setCodes] = useState<string[]>([]);
  const [count, setCount] = useState(0);
  const [targetCount, setTargetCount] = useState<number>(0);
  const [paused, setPaused] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isAggregating, setIsAggregating] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [aggregationResult, setAggregationResult] = useState<AggregationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionTested, setConnectionTested] = useState(false);
  const [autoMode, setAutoMode] = useState(false);
  const [autoProgress, setAutoProgress] = useState<number>(0);
  const [showCountdown, setShowCountdown] = useState(false);
  const [countdown, setCountdown] = useState(3);
  const [lastAggregationTime, setLastAggregationTime] = useState<number>(0);
  const [ssccList, setSsccList] = useState<SsccRecord[]>([]);
  const [boxCount, setBoxCount] = useState<number>(0);
  const [currentBoxNumber, setCurrentBoxNumber] = useState<number>(1);
  const [alreadyScannedCodes, setAlreadyScannedCodes] = useState<Set<string>>(new Set());

  const seenRef = useRef<Set<string>>(new Set());
  const flashRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<number | null>(null);
  const isAggregatingRef = useRef<boolean>(false);
  const scannerContainerRef = useRef<HTMLDivElement>(null);
  const errorTimeoutRef = useRef<number | null>(null);
  const codesRef = useRef<string[]>([]);
  const alreadyScannedCodesRef = useRef<Set<string>>(new Set());
  const shouldSkipAggregationRef = useRef<boolean>(false);

  // ============ ПРОВЕРКА СОЕДИНЕНИЯ С СЕРВЕРОМ ============
  const testServerConnection = useCallback(async () => {
    try {
      const testUrls = [
        `${API_BASE_URL}/health`,
        `${API_BASE_URL}/docs`,
        `${API_BASE_URL}/camera/scan`
      ];

      for (const url of testUrls) {
        try {
          const response = await fetch(url, { method: 'GET' });
          if (response.ok) {
            return true;
          }
        } catch (e) {
          // Продолжаем проверку других URL
        }
      }

      return false;
    } catch (error) {
      console.error('Ошибка проверки соединения:', error);
      return false;
    }
  }, []);

  // ============ ИНИЦИАЛИЗАЦИЯ ============
  useEffect(() => {
    const initializeApp = async () => {
      try {
        // Загружаем сохраненные коды текущей коробки
        const savedCodes = localStorage.getItem(STORAGE_KEY);
        if (savedCodes) {
          try {
            const parsed = JSON.parse(savedCodes) as string[];
            setCodes(parsed);
            codesRef.current = parsed;
            setCount(parsed.length);
            seenRef.current = new Set(parsed);
          } catch (e) {
            console.error('Ошибка чтения кодов из localStorage:', e);
          }
        }

        // Загружаем сохраненное целевое количество
        const savedTarget = localStorage.getItem(STORAGE_TARGET_KEY);
        if (savedTarget) {
          const parsed = parseInt(savedTarget);
          if (!isNaN(parsed) && parsed > 0) {
            setTargetCount(parsed);
            setAutoMode(true);
          }
        }

        // Загружаем историю SSCC кодов
        const savedSsccList = localStorage.getItem(STORAGE_SSCC_LIST_KEY);
        if (savedSsccList) {
          try {
            const parsed = JSON.parse(savedSsccList) as SsccRecord[];
            setSsccList(parsed);
            setBoxCount(parsed.length);
            if (parsed.length > 0) {
              setCurrentBoxNumber(parsed.length + 1);
            }
          } catch (e) {
            console.error('Ошибка чтения SSCC списка:', e);
          }
        }

        // Проверяем соединение с сервером
        const isConnected = await testServerConnection();
        setConnectionTested(isConnected);
      } catch (error) {
        console.error('Ошибка инициализации:', error);
      }
    };

    initializeApp();
  }, [testServerConnection]);

  // Синхронизация alreadyScannedCodes с ref
  useEffect(() => {
    alreadyScannedCodesRef.current = alreadyScannedCodes;
  }, [alreadyScannedCodes]);

  // Сохраняем коды текущей коробки в localStorage и обновляем ref
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(codes));
      codesRef.current = codes;
      setCount(codes.length);
    } catch (e) {
      console.error('Ошибка сохранения кодов:', e);
    }
  }, [codes]);

  // Сохраняем целевое количество в localStorage
  useEffect(() => {
    try {
      if (targetCount > 0) {
        localStorage.setItem(STORAGE_TARGET_KEY, targetCount.toString());
      } else {
        localStorage.removeItem(STORAGE_TARGET_KEY);
      }
    } catch (e) {
      console.error('Ошибка сохранения целевого количества:', e);
    }
  }, [targetCount]);

  // Сохраняем список SSCC в localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_SSCC_LIST_KEY, JSON.stringify(ssccList));
    } catch (e) {
      console.error('Ошибка сохранения SSCC списка:', e);
    }
  }, [ssccList]);

  // ============ ОЧИСТКА СООБЩЕНИЯ ОБ ОШИБКЕ ============
  const clearErrorAfterDelay = () => {
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current);
    }

    errorTimeoutRef.current = window.setTimeout(() => {
      setError(null);
    }, 5000);
  };

  // ============ ДОБАВЛЕНИЕ SSCC В СПИСОК ============
  const addSsccToList = (ssccRecord: Omit<SsccRecord, 'id'>) => {
    const newId = ssccList.length > 0 ? Math.max(...ssccList.map(item => item.id)) + 1 : 1;
    const newRecord: SsccRecord = {
      ...ssccRecord,
      id: newId
    };

    setSsccList(prev => [newRecord, ...prev]);
    setBoxCount(prev => prev + 1);
    setCurrentBoxNumber(prev => prev + 1);
  };

  // ============ ОБНОВЛЕНИЕ ПРОГРЕСС-БАРА ============
  useEffect(() => {
    if (targetCount > 0) {
      const progress = Math.min(100, (codes.length / targetCount) * 100);
      setAutoProgress(progress);
    } else {
      setAutoProgress(0);
    }
  }, [codes.length, targetCount]);

  // ============ ТРИГГЕР АВТОМАТИЧЕСКОЙ АГРЕГАЦИИ ============
  const triggerAutomaticAggregation = async () => {
    if (codesRef.current.length === 0 || !connectionTested || shouldSkipAggregationRef.current) return;

    console.log(`🎯 Автоматическая агрегация! Достигнуто ${codesRef.current.length}/${targetCount} кодов`);

    // Выполняем агрегацию с пометкой что это авто-режим
    await performAggregation(true);
  };

  // ============ АВТОМАТИЧЕСКАЯ ПРОВЕРКА НА ДОСТИЖЕНИЕ ЦЕЛИ ============
  useEffect(() => {
    if (!autoMode || targetCount <= 0 || !connectionTested || isAggregating) return;

    // Используем codesRef.current для получения актуального значения
    if (codesRef.current.length === targetCount) {
      // ПРОВЕРКА: все ли коды уже были использованы ранее?
      const allCodesAlreadyUsed = codesRef.current.every(code => alreadyScannedCodesRef.current.has(code));

      if (allCodesAlreadyUsed) {
        console.log('⚠️ Все коды уже были использованы ранее, пропускаем автоматическую агрегацию');
        setError('Все коды уже были использованы в предыдущих коробках');
        clearErrorAfterDelay();

        // Устанавливаем флаг, чтобы не запускать агрегацию
        shouldSkipAggregationRef.current = true;

        // Очищаем текущую коробку через 1 секунду
        setTimeout(() => {
          startNewBox();
          shouldSkipAggregationRef.current = false;
        }, 1000);
        return;
      }

      // Показываем обратный отсчет перед автоматической агрегацией
      setShowCountdown(true);
      setCountdown(3);

      countdownRef.current = window.setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            if (countdownRef.current) {
              clearInterval(countdownRef.current);
              countdownRef.current = null;
            }
            setShowCountdown(false);
            triggerAutomaticAggregation();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, [codes.length, targetCount, autoMode, connectionTested, isAggregating]);

  // ============ ОБРАБОТКА СКАНИРОВАНИЯ ============
  const handleScan = useCallback((detected: any[]) => {
    if (paused) return;

    let hasNew = false;
    const newCodes: string[] = [];

    for (const item of detected) {
      if (item.format !== 'data_matrix') continue;

      const text = item.rawValue?.trim();
      if (!text) continue;

      // ПРОВЕРКА 1: Уже сканировали в этой коробке?
      if (seenRef.current.has(text)) {
        console.log(`Код уже отсканирован в этой коробке: ${text.substring(0, 20)}...`);
        continue;
      }

      // ПРОВЕРКА 2: Уже сканировали в предыдущих коробках?
      if (alreadyScannedCodesRef.current.has(text)) {
        console.log(`Код уже был сканирован в предыдущих коробках: ${text.substring(0, 20)}...`);

        // Показываем предупреждение, но не блокируем полностью
        if (error === null) {
          setError(`⚠️ Код ${text.substring(0, 20)}... уже был сканирован ранее. Пропускаем.`);
          clearErrorAfterDelay();
        }
        continue;
      }

      // ПРОВЕРКА 3: В автоматическом режиме превышение лимита?
      if (autoMode && targetCount > 0) {
        // Используем codesRef.current для получения актуального количества
        const currentTotal = codesRef.current.length + newCodes.length;
        if (currentTotal >= targetCount) {
          if (error === null) {
            setError(`⚠️ Достигнут лимит в ${targetCount} кодов! Очистите коробку.`);
            clearErrorAfterDelay();
          }
          continue;
        }
      }

      seenRef.current.add(text);
      hasNew = true;
      newCodes.push(text);
    }

    if (hasNew) {
      setCodes(prev => [...newCodes, ...prev]);

      // Визуальная и тактильная обратная связь
      if (flashRef.current) {
        flashRef.current.classList.add("active");
        setTimeout(() => flashRef.current?.classList.remove("active"), 80);
      }
      if (navigator.vibrate) {
        navigator.vibrate([80]);
      }
    }
  }, [paused, autoMode, targetCount, error]);

  // ============ ОТРИСОВКА ОВЕРЛЕЯ ДЛЯ НАЙДЕННЫХ КОДОВ ============
  const drawOverlay = (detected: any[], ctx: CanvasRenderingContext2D) => {
    detected.forEach(item => {
      if (item.format !== 'data_matrix') return;
      const { x, y, width, height } = item.boundingBox;
      ctx.strokeStyle = '#00ff00';
      ctx.lineWidth = 4;
      ctx.setLineDash([8, 6]);
      ctx.strokeRect(x - 3, y - 3, width + 6, height + 6);
      ctx.setLineDash([]);
    });
  };

  // ============ НАЧАТЬ НОВУЮ КОРОБКУ ============
  const startNewBox = () => {
    console.log('🚀 Начинаем новую коробку');

    setCodes([]);
    codesRef.current = [];
    seenRef.current.clear();
    localStorage.removeItem(STORAGE_KEY);
    setScanResult(null);
    setAggregationResult(null);
    setError(null);
    setShowCountdown(false);
    setCountdown(3);
    setAutoProgress(0);

    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  };

  // ============ ОЧИСТКА ТЕКУЩЕЙ КОРОБКИ ============
  const clearCurrentBox = () => {
    if (codes.length === 0) return;

    if (confirm('Очистить текущую коробку? Список SSCC кодов останется нетронутым.')) {
      setCodes([]);
      codesRef.current = [];
      seenRef.current.clear();
      localStorage.removeItem(STORAGE_KEY);
      setScanResult(null);
      setAggregationResult(null);
      setError(null);
      setShowCountdown(false);
      setCountdown(3);
      setAutoProgress(0);

      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    }
  };

  // ============ ОЧИСТКА ВСЕЙ ИСТОРИИ ============
  const clearAllHistory = () => {
    if (confirm('Очистить всю историю? Это удалит все SSCC коды и текущую коробку.')) {
      setCodes([]);
      codesRef.current = [];
      seenRef.current.clear();
      setAlreadyScannedCodes(new Set());
      alreadyScannedCodesRef.current = new Set();
      setSsccList([]);
      setBoxCount(0);
      setCurrentBoxNumber(1);
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_SSCC_LIST_KEY);
      setScanResult(null);
      setAggregationResult(null);
      setError(null);
      setShowCountdown(false);
      setCountdown(3);
      setAutoProgress(0);

      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    }
  };

  // ============ ПРОВЕРКА КОДОВ НА СЕРВЕРЕ ============
  const checkCodes = async () => {
    if (codesRef.current.length === 0) {
      setError('Нет отсканированных кодов для проверки');
      return;
    }

    if (!connectionTested) {
      setError('Сервер недоступен. Проверьте подключение.');
      return;
    }

    setIsChecking(true);
    setError(null);
    setAggregationResult(null);

    try {
      const url = `${API_BASE_URL}/api/v1/camera/scan`;

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          codes: codesRef.current,
          device_id: 'mobile_scanner'
        }),
      });

      if (!response.ok) {
        let errorText = 'Пустой ответ';
        try {
          const errorData = await response.json();
          errorText = errorData.detail || errorData.error || `${response.status}: ${response.statusText}`;
        } catch (e) {
          errorText = await response.text().catch(() => `${response.status}: ${response.statusText}`);
        }

        throw new Error(errorText);
      }

      const data: ScanResponse = await response.json();
      setScanResult(data);

    } catch (err: any) {
      let errorMessage = 'Ошибка при проверке кодов';

      if (err.name === 'TypeError' && err.message.includes('Failed to fetch')) {
        errorMessage = 'Не удалось подключиться к серверу. Проверьте:\n';
        errorMessage += `1. Запущен ли сервер на ${API_BASE_URL}\n`;
        errorMessage += '2. Правильно ли настроен CORS на сервере\n';
        errorMessage += '3. iOS Safari может блокировать HTTP запросы\n';
        errorMessage += '4. Проверьте настройки брандмауэра';
      } else if (err.message) {
        errorMessage = err.message;
      }

      setError(errorMessage);
    } finally {
      setIsChecking(false);
    }
  };

  // ============ ВЫПОЛНЕНИЕ АГРЕГАЦИИ ============
  const performAggregation = async (isAuto: boolean = false) => {
    // Останавливаем обратный отсчет, если он запущен
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    setShowCountdown(false);

    // ПРОВЕРКА 1: Есть ли коды?
    if (codesRef.current.length === 0) {
      setError('Нет отсканированных кодов для агрегации');
      return;
    }

    // ПРОВЕРКА 2: Автоматический режим с лимитом
    if (autoMode && targetCount > 0 && codesRef.current.length !== targetCount) {
      setError(`⚠️ В автоматическом режиме требуется ровно ${targetCount} кодов. Сейчас: ${codesRef.current.length}`);
      clearErrorAfterDelay();
      return;
    }

    // ПРОВЕРКА 3: Сервер доступен?
    if (!connectionTested) {
      setError('Сервер недоступен. Проверьте подключение.');
      return;
    }

    // ПРОВЕРКА 4: Защита от слишком частых запросов
    const now = Date.now();
    if (now - lastAggregationTime < 3000) {
      setError('Пожалуйста, подождите 3 секунды перед следующей агрегацией');
      clearErrorAfterDelay();
      return;
    }

    // ПРОВЕРКА 5: Защита от одновременных запросов
    if (isAggregatingRef.current) {
      setError('Агрегация уже выполняется. Пожалуйста, подождите.');
      return;
    }

    // Устанавливаем блокировку
    isAggregatingRef.current = true;
    setLastAggregationTime(now);
    setIsAggregating(true);
    setError(null);
    setAggregationResult(null);

    try {
      const url = `${API_BASE_URL}/api/v1/camera/scan/aggregation`;

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          codes: codesRef.current,
          device_id: 'mobile_scanner'
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        // ВАЖНО: Даже при ошибке добавляем коды в alreadyScannedCodes
        if (response.status === 400 || response.status === 409) {
          const newSet = new Set(alreadyScannedCodesRef.current);
          codesRef.current.forEach(code => newSet.add(code));
          setAlreadyScannedCodes(newSet);
          alreadyScannedCodesRef.current = newSet;
        }

        let errorText = data.detail || data.error || data.message || `${response.status}: ${response.statusText}`;
        throw new Error(errorText);
      }

      setAggregationResult(data);

      // Обработка разных сценариев
      if (data.print_status === 'already_exists') {
        // Коробка уже существует - добавляем коды в alreadyScannedCodes
        const newSet = new Set(alreadyScannedCodesRef.current);
        codesRef.current.forEach(code => newSet.add(code));
        setAlreadyScannedCodes(newSet);
        alreadyScannedCodesRef.current = newSet;

        // Начинаем новую коробку
        startNewBox();

      } else if (data.success) {
        // Новая коробка успешно создана
        alert(`✅ ${isAuto ? 'Автоматическая ' : ''}Коробка успешно создана!\n\n` +
              `ID коробки: ${data.box_id}\n` +
              `SSCC-код: ${data.sscc_code}\n` +
              `Заказ: ${data.order_id}\n\n` +
              `${data.print_status === 'sent_to_printer'
                ? 'Задание на печать SSCC-кода отправлено на принтер'
                : 'Печать SSCC-кода ожидает'}`);

        // Добавляем SSCC в историю
        if (data.sscc_code && data.box_id) {
          const ssccRecord: Omit<SsccRecord, 'id'> = {
            code: data.sscc_code,
            box_id: data.box_id,
            order_id: data.order_id,
            timestamp: new Date().toLocaleString(),
            total_codes: data.total_codes_scanned
          };
          addSsccToList(ssccRecord);
        }

        // Добавляем коды в alreadyScannedCodes
        const newSet = new Set(alreadyScannedCodesRef.current);
        codesRef.current.forEach(code => newSet.add(code));
        setAlreadyScannedCodes(newSet);
        alreadyScannedCodesRef.current = newSet;

        // Начинаем новую коробку
        startNewBox();
      }

    } catch (err: any) {
      let errorMessage = 'Ошибка при выполнении агрегации';

      if (err.name === 'TypeError' && err.message.includes('Failed to fetch')) {
        errorMessage = 'Не удалось подключиться к серверу. Проверьте:\n';
        errorMessage += `1. Запущен ли сервер на ${API_BASE_URL}\n`;
        errorMessage += '2. Правильно ли настроен CORS на сервере\n';
        errorMessage += '3. iOS Safari может блокировать HTTP запросы\n';
        errorMessage += '4. Проверьте настройки брандмауэра';
      } else if (err.message) {
        errorMessage = err.message;
      }

      setError(errorMessage);
      console.error('Ошибка агрегации:', err);

      // При ЛЮБОЙ ошибке очищаем коробку (после добавления кодов в alreadyScannedCodes)
      startNewBox();
    } finally {
      // Снимаем блокировку
      isAggregatingRef.current = false;
      setIsAggregating(false);
    }
  };

  // ============ АВТОМАТИЧЕСКАЯ ПРОВЕРКА НА ДОСТИЖЕНИЕ ЦЕЛИ ============
  useEffect(() => {
    if (!autoMode || targetCount <= 0 || !connectionTested || isAggregating) return;

    // Используем codesRef.current для получения актуального значения
    if (codesRef.current.length === targetCount) {
      // ПРОВЕРКА: все ли коды уже были использованы ранее?
      const allCodesAlreadyUsed = codesRef.current.every(code => alreadyScannedCodesRef.current.has(code));

      if (allCodesAlreadyUsed) {
        console.log('⚠️ Все коды уже были использованы ранее, очищаем коробку');

        // Очищаем текущую коробку сразу (без задержки)
        startNewBox();
        return;
      }

      // Показываем обратный отсчет перед автоматической агрегацией
      setShowCountdown(true);
      setCountdown(3);

      countdownRef.current = window.setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            if (countdownRef.current) {
              clearInterval(countdownRef.current);
              countdownRef.current = null;
            }
            setShowCountdown(false);
            performAggregation(true); // Прямой вызов, не через triggerAutomaticAggregation
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, [codes.length, targetCount, autoMode, connectionTested, isAggregating]);

  // ============ ФУНКЦИЯ ПОВТОРНОЙ ПЕЧАТИ SSCC ============
  const retryPrintSSCC = async (boxId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/camera/print/retry/${boxId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          device_id: 'mobile_scanner'
        }),
      });

      if (!response.ok) {
        let errorText = 'Пустой ответ';
        try {
          const errorData = await response.json();
          errorText = errorData.detail || errorData.error || `${response.status}: ${response.statusText}`;
        } catch (e) {
          errorText = await response.text().catch(() => `${response.status}: ${response.statusText}`);
        }
        throw new Error(errorText);
      }

      const result = await response.json();

      if (result.success) {
        alert(`✅ Задание на повторную печать SSCC отправлено!\nКоробка: ${boxId}\nSSCC: ${result.sscc_code}`);
      } else {
        alert(`❌ Не удалось отправить задание на печать: ${result.message}`);
      }

    } catch (error: any) {
      console.error('Ошибка повторной печати:', error);
      alert('Не удалось отправить задание на печать. Проверьте подключение к серверу.');
    }
  };

  // ============ ПОВТОРНАЯ ПРОВЕРКА СОЕДИНЕНИЯ ============
  const retryConnection = async () => {
    setError(null);
    const isConnected = await testServerConnection();
    setConnectionTested(isConnected);

    if (!isConnected) {
      setError('Сервер недоступен. Проверьте подключение к сети и запуск сервера.');
    }
  };

  // ============ КОПИРОВАНИЕ SSCC В БУФЕР ============
  const copySSCCToClipboard = (ssccCode: string) => {
    navigator.clipboard.writeText(ssccCode)
      .then(() => {
        alert('SSCC-код скопирован в буфер обмена!');
      })
      .catch(err => {
        console.error('Ошибка копирования:', err);
        alert('Не удалось скопировать SSCC-код');
      });
  };

  // ============ КОПИРОВАНИЕ ВСЕХ SSCC В БУФЕР ============
  const copyAllSSCCText = () => {
    const text = ssccList.map(record => `${record.code} - Коробка #${record.box_id} - ${record.timestamp}`).join('\n');
    navigator.clipboard.writeText(text)
      .then(() => {
        alert('Все SSCC-коды скопированы в буфер обмена!');
      })
      .catch(err => {
        console.error('Ошибка копирования:', err);
        alert('Не удалось скопировать SSCC-коды');
      });
  };

  // ============ УПРАВЛЕНИЕ АВТОМАТИЧЕСКИМ РЕЖИМОМ ============
  const toggleAutoMode = () => {
    if (autoMode) {
      // Выключаем авторежим
      setAutoMode(false);
      setTargetCount(0);
      setShowCountdown(false);
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    } else {
      // Включаем авторежим, запрашиваем количество
      const input = prompt('Введите количество кодов для автоматической агрегации:', targetCount > 0 ? targetCount.toString() : '3');
      if (input) {
        const count = parseInt(input);
        if (!isNaN(count) && count > 0) {
          // Проверяем, что установленный лимит не меньше уже отсканированных кодов
          if (count < codesRef.current.length) {
            alert(`Невозможно установить лимит ${count}, так как уже отсканировано ${codesRef.current.length} кодов.`);
            return;
          }
          setTargetCount(count);
          setAutoMode(true);
        } else {
          alert('Пожалуйста, введите корректное число больше 0');
        }
      }
    }
  };

  // ============ СБРОС ТАЙМЕРА ОТСЧЕТА ============
  const cancelCountdown = () => {
    setShowCountdown(false);
    setCountdown(3);
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  };

  // ============ КОПИРОВАНИЕ ВСЕХ КОДОВ В БУФЕР ============
  const copyAllCodesToClipboard = () => {
    const text = codesRef.current.join('\n');
    navigator.clipboard.writeText(text)
      .then(() => {
        alert('Коды текущей коробки скопированы в буфер обмена!');
      })
      .catch(err => {
        console.error('Ошибка копирования:', err);
        alert('Не удалось скопировать коды');
      });
  };

  // ============ ОБНОВЛЕНИЕ ЦЕЛЕВОГО КОЛИЧЕСТВА ============
  const updateTargetCount = () => {
    const input = prompt('Изменить количество кодов:', targetCount.toString());
    if (input) {
      const count = parseInt(input);
      if (!isNaN(count) && count > 0) {
        // Проверяем, что установленный лимит не меньше уже отсканированных кодов
        if (count < codesRef.current.length) {
          alert(`Невозможно установить лимит ${count}, так как уже отсканировано ${codesRef.current.length} кодов.`);
          return;
        }
        setTargetCount(count);
      } else {
        alert('Пожалуйста, введите корректное число больше 0');
      }
    }
  };

  return (
    <div className="app">
      {/* ЯРКИЙ СЧЕТЧИК КОРОБОК */}
      <div className="box-counter-container">
        <div className="box-counter">
          <div className="counter-label">ОТСКАНИРОВАНО КОРОБОК</div>
          <div className="counter-number">{boxCount}</div>
          <div className="counter-subtext">Текущая коробка: #{currentBoxNumber}</div>
        </div>
      </div>

      <div className="app-content">
        {/* ЛЕВАЯ ПАНЕЛЬ - ИНФОРМАЦИЯ */}
        <div className="left-panel">
          <header className="header">
            <h1>📦 Сканер коробок</h1>

            {/* Статус соединения */}
            <div className="connection-status">
              <div className={`status-indicator ${connectionTested ? 'connected' : 'disconnected'}`}>
                {connectionTested ? '✅ Сервер доступен' : '❌ Сервер недоступен'}
              </div>
              <button onClick={retryConnection} className="retry-connection-btn" title="Проверить подключение">
                🔄
              </button>
            </div>

            <div className="stats">
              <span className="count">Кодов в текущей коробке: {count}</span>
              <button onClick={startNewBox} className="new-box-btn" title="Начать новую коробку">
                🆕 Новая коробка
              </button>
              <button onClick={clearCurrentBox} className="clear-btn" title="Очистить текущую коробку">
                Очистить
              </button>
            </div>
          </header>

          {/* Автоматический режим */}
          <div className="auto-mode-section">
            <div className="auto-mode-toggle">
              <button
                onClick={toggleAutoMode}
                className={`auto-mode-btn ${autoMode ? 'active' : ''}`}
                title={autoMode ? 'Выключить автоматический режим' : 'Включить автоматический режим'}
              >
                {autoMode ? '🔄 Автоматический режим ВКЛ' : '⏸️ Автоматический режим ВЫКЛ'}
              </button>

              {autoMode && targetCount > 0 && (
                <div className="auto-mode-info">
                  <span>Цель: ровно {targetCount} кодов</span>
                  <button
                    onClick={updateTargetCount}
                    className="edit-target-btn"
                    title="Изменить количество кодов"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => {
                      setAutoMode(false);
                      setTargetCount(0);
                      setShowCountdown(false);
                      if (countdownRef.current) {
                        clearInterval(countdownRef.current);
                        countdownRef.current = null;
                      }
                    }}
                    className="cancel-auto-btn"
                    title="Отменить автоматический режим"
                  >
                    ❌
                  </button>
                </div>
              )}
            </div>

            {autoMode && targetCount > 0 && (
              <div className="auto-progress">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${autoProgress}%` }}
                  ></div>
                </div>
                <div className="progress-text">
                  {codes.length} / {targetCount} ({Math.round(autoProgress)}%)
                  {autoProgress >= 100 && ' - ГОТОВО!'}
                </div>
              </div>
            )}
          </div>

          {/* Уведомление о том, что все коды уже использованы */}
          {autoMode && targetCount > 0 && codes.length > 0 &&
            codes.every(code => alreadyScannedCodesRef.current.has(code)) && (
            <div className="warning-message">
              ⚠️ Все коды в текущей коробке уже были использованы ранее.
              Коробка будет автоматически очищена.
            </div>
          )}

          {/* Окно обратного отсчета */}
          {showCountdown && (
            <div className="countdown-overlay">
              <div className="countdown-modal">
                <h2>Автоматическая агрегация через...</h2>
                <div className="countdown-number">{countdown}</div>
                <p>Достигнуто необходимое количество кодов</p>
                <div className="countdown-actions">
                  <button onClick={cancelCountdown} className="cancel-btn">
                    Отменить
                  </button>
                  <button onClick={() => {
                    cancelCountdown();
                    triggerAutomaticAggregation();
                  }} className="proceed-btn">
                    Выполнить сейчас
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Предупреждение если сервер недоступен */}
          {!connectionTested && (
            <div className="connection-warning">
              <p>⚠️ Сервер недоступен</p>
              <p>URL: {API_BASE_URL}</p>
              <button onClick={retryConnection} className="retry-btn">
                Повторить подключение
              </button>
            </div>
          )}

          {/* Кнопки действий */}
          <div className="action-section">
            <div className="action-buttons">
              <button
                onClick={checkCodes}
                className="check-btn"
                disabled={isChecking || codesRef.current.length === 0 || !connectionTested}
                title="Проверить коды в базе данных"
              >
                {isChecking ? (
                  <>
                    <span className="loading-spinner"></span>
                    Проверка...
                  </>
                ) : (
                  '🔍 Проверить коды'
                )}
              </button>

              <button
                onClick={() => performAggregation(false)}
                className="aggregate-btn"
                disabled={isAggregating || codesRef.current.length === 0 || !connectionTested}
                title="Создать коробку с отсканированными кодами и автоматически напечатать SSCC"
              >
                {isAggregating ? (
                  <>
                    <span className="loading-spinner"></span>
                    Агрегация...
                  </>
                ) : (
                  '📦 Создать коробку'
                )}
              </button>
            </div>

            {error && (
              <div className="error-message">
                <div className="error-details">{error}</div>
              </div>
            )}
          </div>

          {/* Результаты проверки */}
          {scanResult && (
            <section className="scan-results">
              <h3>Результаты проверки:</h3>

              <div className="scan-summary">
                <div className="summary-item">
                  <span className="summary-label">Всего кодов:</span>
                  <span className="summary-value">{scanResult.total_codes}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Найдено:</span>
                  <span className="summary-value success">{scanResult.found_codes}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Не найдено:</span>
                  <span className="summary-value warning">{scanResult.not_found_codes.length}</span>
                </div>
              </div>
            </section>
          )}

          {/* Результаты агрегации с SSCC */}
          {aggregationResult && (
            <section className="aggregation-results">
              <h3>
                {aggregationResult.print_status === 'already_exists'
                  ? 'ℹ️ Коробка уже существует'
                  : '✅ Коробка успешно создана!'}
              </h3>

              <div className="sscc-display">
                <div className="sscc-header">
                  <span className="sscc-label">SSCC Код:</span>
                  <span className="sscc-status">
                    {aggregationResult.print_status === 'sent_to_printer'
                      ? '🖨️ Печать запущена'
                      : aggregationResult.print_status === 'already_exists'
                      ? '✅ Уже существует'
                      : '⏳ Ожидает печати'}
                  </span>
                </div>
                <div className="sscc-code" onClick={() => copySSCCToClipboard(aggregationResult.sscc_code)}>
                  {aggregationResult.sscc_code}
                  <span className="copy-hint">(клик для копирования)</span>
                </div>
              </div>
            </section>
          )}

          {/* СПИСОК SSCC КОДОВ */}
          <section className="sscc-list-section">
            <div className="section-header">
              <h3>📋 История коробок ({ssccList.length})</h3>
              {ssccList.length > 0 && (
                <button
                  onClick={copyAllSSCCText}
                  className="copy-all-btn"
                  title="Копировать все SSCC коды"
                >
                  📋 Копировать все
                </button>
              )}
            </div>

            {ssccList.length === 0 ? (
              <p className="empty-list">Здесь будут появляться SSCC коды созданных коробок</p>
            ) : (
              <div className="sscc-list-container">
                {ssccList.map((record) => (
                  <div key={record.id} className="sscc-record">
                    <div className="sscc-record-header">
                      <span className="sscc-record-code" onClick={() => copySSCCToClipboard(record.code)}>
                        {record.code}
                      </span>
                      <span className="sscc-record-date">{record.timestamp}</span>
                    </div>
                    <div className="sscc-record-details">
                      <span className="detail">Коробка #{record.box_id}</span>
                      <span className="detail">Заказ #{record.order_id}</span>
                      <span className="detail">Кодов: {record.total_codes}</span>
                      <button
                        onClick={() => retryPrintSSCC(record.box_id)}
                        className="retry-print-btn"
                        title="Повторить печать SSCC-кода"
                      >
                        🖨️ Печатать
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Список отсканированных кодов текущей коробки */}
          <section className="scanned-codes">
            <div className="scanned-header">
              <h3>Коды текущей коробки ({codes.length}):</h3>
              {codes.length > 0 && (
                <button
                  onClick={copyAllCodesToClipboard}
                  className="copy-btn"
                  title="Копировать все коды в буфер обмена"
                >
                  📋 Копировать
                </button>
              )}
            </div>

            {codes.length === 0 ? (
              <p className="empty">
                {aggregationResult
                  ? '✅ Коробка успешно создана! Начинайте сканировать следующую коробку.'
                  : 'Пока ничего не отсканировано. Наведите камеру на DataMatrix код'
                }
              </p>
            ) : (
              <div className="codes-container">
                {codes.slice(0, 10).map((code, i) => (
                  <div key={i} className="code-item">
                    <span className="code-index">{i + 1}.</span>
                    <span className="code-text">{code}</span>
                  </div>
                ))}
                {codes.length > 10 && (
                  <div className="more-indicator">
                    ... и еще {codes.length - 10} кодов
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Кнопка очистки всей истории */}
          <button
            onClick={clearAllHistory}
            className="clear-history-btn"
            title="Очистить всю историю (SSCC и текущую коробку)"
          >
            🗑️ Очистить всю историю
          </button>
        </div>

        {/* ПРАВАЯ ПАНЕЛЬ - КАМЕРА */}
        <div className="right-panel">
          <div className="scanner-container" ref={scannerContainerRef}>
            <div className="scanner-header">
              <h2>📷 Камера для сканирования</h2>
              <div className="scanner-status">
                <span className={`status-dot ${paused ? 'paused' : 'active'}`}></span>
                {paused ? 'Пауза' : 'Сканирование активно'}
              </div>
            </div>

            <div ref={flashRef} className="flash" />

            {/* Сканер */}
            <div className="scanner-wrapper">
              <Scanner
                onScan={handleScan}
                formats={['data_matrix']}
                paused={paused}
                scanDelay={180}
                sound={true}
                constraints={{ facingMode: 'environment' }}
                components={{
                  tracker: drawOverlay,
                  finder: false,

                  torch: true,
                  zoom: true,
                  onOff: true,
                }}
                styles={{
                  container: { borderRadius: '12px', overflow: 'hidden', width: '100%', height: '100%' },
                }}
              />
            </div>

            {/* Инструкция */}
            <div className="scanner-instructions">
              <p>Наведите камеру на DataMatrix код коробки</p>
              <p>Каждый отсканированный код добавляется в текущую коробку</p>
              {autoMode && targetCount > 0 && (
                <p className="limit-info">
                  ⚠️ Требуется ровно {targetCount} кодов. Сейчас: {codes.length}/{targetCount}
                </p>
              )}
            </div>

            {/* Кнопка паузы */}
            <button
              onClick={() => setPaused(!paused)}
              className="pause-btn"
              title={paused ? 'Возобновить сканирование' : 'Приостановить сканирование'}
            >
              {paused ? '▶️ Возобновить сканирование' : '⏸️ Приостановить'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;