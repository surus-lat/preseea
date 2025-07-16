## Preseea

Este script te permite recolectar archivos de texto y audio del corpus PRESEEA. Utiliza técnicas de web scraping para hacer llamadas a la web de [PRESEEA](https://preseea.uah.es/corpus/) y descargar los archivos relevantes.

Podés encontrar al dataset ya recolectado en HuggingFace: [PRESEEA Dataset](https://huggingface.co/datasets/marianbasti/preseea).

### Requisitos

- Python 3.x
- Bibliotecas: `requests`, `beautifulsoup4`

### Uso

1. Clona este repositorio.
2. Instala las dependencias:
   ```
   pip install requests beautifulsoup4
   ```
3. Ejecuta el script:
   ```
   python preseea.py
   ```
   Esto descargará el dataset con el siguiente formato:
   ```
    ./preseea/
    ├── Argentina
    │   ├── utterance1
    │   │   ├── file1.txt
    │   │   └── file1.mp3
    │   ├── utterance2
    │   │   ├── file2.txt
    │   │   └── file2.mp3
    └── ...
   ```
### Argumentos extra
Podés especificar el país que querés descargar como argumento al script. Por ejemplo, para descargar solo Argentina:
```
python preseea.py --country Argentina
```

También podes especificar cuantas llamadas concurrentes querés hacer al servidor y acelerar el proceso de recolección con el argumento `--concurrency` (cuidado de no abusar). Por ejemplo, para hacer de 5 llamadas concurrentes:
```
python preseea.py --concurrency 5
```

### Cita

```bibtex
@misc{preseea,
  author = {Universidad de Alcalá},
  title = {PRESEEA: Corpus del Proyecto para el estudio sociolingüístico del español de España y de América},
  year = {2014},
  url = {http://preseea.uah.es}
}
```
