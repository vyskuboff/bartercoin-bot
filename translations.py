import json

def get_translation(lang, key, **kwargs):
    translations_file_path = '/translations.json'
    with open(translations_file_path, 'r') as f:
        translations = json.load(f)
    # Используем метод format() для вставки переменных в строку перевода
    return translations[lang][key].format(**kwargs)