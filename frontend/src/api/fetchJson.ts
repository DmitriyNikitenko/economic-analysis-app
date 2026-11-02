// Функция получает файл по указанному адресу,
// проверяет успешность HTTP-запроса и преобразует ответ в JSON 
export async function fetchJson<T>(url: string): Promise<T> {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(`Ошибка загрузки ${url}: HTTP ${response.status}`);
    }

    return (await response.json()) as T;
}