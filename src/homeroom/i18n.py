"""English and Spanish, shipped together, with parity enforced by tests.

About two in five Californians speak a language other than English at home, and
Spanish is by far the largest of them. The families least well served by the
state's own download pages are the ones this project exists for, so translation is
a launch requirement rather than a later phase (README standards table;
docs/ROADMAP.md M4).

The catalogs below are plain dictionaries keyed by locale. The parity gate lives in
``tests/test_i18n.py`` and fails when:

* a key exists in one locale and not the other, in any catalog;
* a Spanish string is left byte-identical to its English original, unless the key
  is on a short reviewed list of words that are genuinely the same in both;
* a template's ``{placeholder}`` set differs between locales, which is how a
  number quietly disappears from a translated sentence;
* a reporting category, grade column, or subgroup family gains a code in the
  pipeline without a name in both languages.

That last one is the important one: the display names are not decoration, they are
what a family reads instead of ``ELAS_RFEP``, and an untranslated code would leave
a Spanish page carrying an English label for a real school.

Nothing here interpolates a number into a sentence that would then need plural
agreement. Counts are rendered as ``label: number`` pairs and in table cells, so a
count never forces a verb to agree with it in two grammars at once.
"""

from __future__ import annotations

from typing import Literal

from homeroom.enrollment import GRADE_COLUMNS
from homeroom.profiles import CATEGORY_NAMES, SUBGROUP_FAMILIES

Locale = Literal["en", "es"]

LOCALES: tuple[Locale, ...] = ("en", "es")
"""Every locale the site renders. Both are peers; neither is a fallback."""

OTHER_LOCALE: dict[Locale, Locale] = {"en": "es", "es": "en"}
"""The locale each page links to. A page with no way out of its language is a
page a reader is trapped on."""

LOCALE_NAMES: dict[Locale, str] = {"en": "English", "es": "Español"}
"""Each locale named in its own language, which is how a language switch is read
by someone who cannot read the page they are on."""

CDE_TEXT_LOCALE: Locale = "en"
"""CDE publishes school, district, county, and city names in English only.

On a Spanish page those names are marked ``lang="en"`` at every render site, so a
Spanish screen reader does not pronounce English words with Spanish phonemes
(WCAG 2.2 SC 3.1.2). :func:`cde_text_lang` returns the attribute value to use, or
``None`` on an English page where it would be redundant.
"""


def cde_text_lang(locale: Locale) -> Locale | None:
    """The ``lang`` to put on CDE-published text, or ``None`` if not needed."""
    return CDE_TEXT_LOCALE if locale != CDE_TEXT_LOCALE else None


UI: dict[Locale, dict[str, str]] = {
    "en": {
        "site_name": "Homeroom",
        "site_tagline": (
            "California public school data, readable by the families it describes."
        ),
        "skip_to_content": "Skip to the main content",
        "language_nav": "Language",
        "switch_language_hint": "Read this page in Spanish",
        "eyebrow": "California public school",
        "page_title": "{school}, {year} school year",
        "meta_description": (
            "Enrollment for {school} in {district}, taken from California Department "
            "of Education public files. No score, no grade, no ranking."
        ),
        "identity_district": "School district",
        "identity_city": "City",
        "identity_county": "County",
        "identity_grades": "Grades served",
        "identity_cds": "County-district-school code",
        "identity_type": "School type",
        "identity_type_charter": "Charter school",
        "identity_type_district": "Not a charter school",
        "fixture_banner_title": "This page was built from test data.",
        "fixture_banner_body": (
            "Nothing on it describes a real school. It exists so the checks that "
            "guard the real pages can run without any acquired file."
        ),
        "how_to_read_heading": "How to read this page",
        "no_ranking_body": (
            "Homeroom does not rank schools. There is no score here, no grade, and no "
            "list putting one school above another. Each figure is shown on its own, "
            "with the public file it came from named at the bottom of the page."
        ),
        "states_intro": (
            "A blank cell is not a zero, and a withheld number is not a zero either. "
            "Those are three different facts, and this page keeps them apart."
        ),
        "states_heading": "What each cell can say",
        "state_number_label": "A number",
        "state_number_body": (
            "The state published this figure. It is printed exactly as published."
        ),
        "state_zero_label": "reported as zero",
        "state_zero_body": (
            "The state published a zero. Nobody was counted, and that is a fact the "
            "state recorded, not an empty space."
        ),
        "state_withheld_label": "withheld to protect privacy",
        "state_withheld_body": (
            "The state has this figure and holds it back, because the group is small "
            "enough that publishing the count could identify a student. Homeroom "
            "leaves it out. It is never filled in and never shown as a zero."
        ),
        "state_nothing_label": "no figure published",
        "state_nothing_body": (
            "The state published nothing here at all. That is different from a zero "
            "and different from a figure held back."
        ),
        "students_heading": "Students",
        "grades_heading": "Students by grade",
        "groups_heading": "Students by group",
        "groups_intro": (
            "These are the groups the state counts, using its own categories. A group "
            "with a small number of students is often withheld, which is why so many "
            "of these rows say so."
        ),
        "col_figure": "Figure",
        "col_grade": "Grade",
        "col_group": "Group",
        "col_this_school": "At this school",
        "col_publishing": "Schools publishing it",
        "col_withholding": "Schools withholding it",
        "col_nothing": "Schools publishing nothing",
        "caption_total": "Total enrollment at {school} on Census Day, {year}.",
        "caption_grades": "Enrollment by grade at {school} on Census Day, {year}.",
        "caption_groups": "{family} at {school} on Census Day, {year}.",
        "coverage_note": (
            "The last three columns are not about this school. They count all "
            "{schools} active schools Homeroom holds, so that an empty row here can "
            "be read against how often the state publishes that figure at all."
        ),
        "coverage_heading": "How much of this the state publishes",
        "coverage_body": (
            "Coverage is published beside the data on purpose. A page that showed "
            "only what exists would read as a complete picture, and it is not one."
        ),
        "coverage_schools": "Active schools in this build",
        "coverage_total_published": "Schools publishing a total enrollment figure",
        "coverage_total_withheld": "Schools where that total is withheld",
        "coverage_total_nothing": "Schools publishing no total at all",
        "coverage_unjoined": "Enrollment records matching no active school",
        "not_yet_heading": "What is not on this page yet",
        "not_yet_assignments": (
            "Teacher assignment data is not yet acquired. California publishes, for "
            "each school, how many teaching assignments were held by a teacher with "
            "a clear credential matched to what they teach. Homeroom can read that "
            "file and has not obtained it, so this page shows no figure about the "
            "teachers at this school and will not until the file is in hand."
        ),
        "not_yet_context": (
            "District and statewide figures are not yet beside each measure. Until "
            "they are, the coverage columns are the only context here."
        ),
        "not_yet_measures": (
            "Chronic absenteeism, the state dashboard indicators, and per-pupil "
            "spending are not here yet either. Each one arrives with its own file "
            "and its own access date, or it does not arrive."
        ),
        "sources_heading": "Where these numbers come from",
        "sources_body": (
            "Every figure above was copied from one of these files. Nothing was "
            "estimated, averaged, or filled in from a neighbouring number."
        ),
        "source_d1_name": "School names and districts",
        "source_d1_title": "Public Schools and Districts directory",
        "source_d2_name": "Enrollment",
        "source_d2_title": "Census Day Enrollment Data",
        "source_file": "File",
        "source_downloaded": "Downloaded",
        "source_year": "School year",
        "source_page": "The state's page for this file",
        "source_fixture": (
            "Test fixture, not an acquired file. No download date, because nobody "
            "downloaded anything."
        ),
        "footer_unaffiliated": (
            "Homeroom is not affiliated with, endorsed by, or connected to the "
            "California Department of Education, the State of California, or any "
            "school district."
        ),
        "footer_no_ranking": (
            "No score, no grade, no ranking. If a figure cannot be shown honestly, "
            "it is not shown."
        ),
    },
    "es": {
        "site_name": "Homeroom",
        "site_tagline": (
            "Datos de las escuelas públicas de California, legibles para las "
            "familias que describen."
        ),
        "skip_to_content": "Saltar al contenido principal",
        "language_nav": "Idioma",
        "switch_language_hint": "Lea esta página en inglés",
        "eyebrow": "Escuela pública de California",
        "page_title": "{school}, ciclo escolar {year}",
        "meta_description": (
            "Matrícula de {school} en {district}, tomada de archivos públicos del "
            "Departamento de Educación de California. Sin puntaje, sin calificación, "
            "sin clasificación."
        ),
        "identity_district": "Distrito escolar",
        "identity_city": "Ciudad",
        "identity_county": "Condado",
        "identity_grades": "Grados que ofrece",
        "identity_cds": "Código de condado, distrito y escuela",
        "identity_type": "Tipo de escuela",
        "identity_type_charter": "Escuela chárter",
        "identity_type_district": "No es una escuela chárter",
        "fixture_banner_title": "Esta página se creó con datos de prueba.",
        "fixture_banner_body": (
            "Nada de lo que aparece aquí describe a una escuela real. Existe para "
            "que las verificaciones que protegen las páginas reales puedan "
            "ejecutarse sin ningún archivo obtenido."
        ),
        "how_to_read_heading": "Cómo leer esta página",
        "no_ranking_body": (
            "Homeroom no clasifica a las escuelas. Aquí no hay puntaje, ni "
            "calificación, ni una lista que ponga una escuela por encima de otra. "
            "Cada dato se muestra por sí solo, y al final de la página se nombra el "
            "archivo público del que salió."
        ),
        "states_intro": (
            "Una celda vacía no es un cero, y un dato retenido tampoco es un cero. "
            "Son tres hechos distintos, y esta página los mantiene separados."
        ),
        "states_heading": "Lo que puede decir cada celda",
        "state_number_label": "Un número",
        "state_number_body": (
            "El estado publicó este dato. Aparece tal como se publicó."
        ),
        "state_zero_label": "informado como cero",
        "state_zero_body": (
            "El estado publicó un cero. No se contó a nadie, y eso es un hecho que "
            "el estado registró, no un espacio en blanco."
        ),
        "state_withheld_label": "retenido para proteger la privacidad",
        "state_withheld_body": (
            "El estado tiene este dato y lo retiene, porque el grupo es tan pequeño "
            "que publicar la cifra podría identificar a un estudiante. Homeroom lo "
            "deja fuera. Nunca se rellena ni se muestra como un cero."
        ),
        "state_nothing_label": "sin dato publicado",
        "state_nothing_body": (
            "El estado no publicó nada aquí. Eso es distinto de un cero y distinto "
            "de un dato retenido."
        ),
        "students_heading": "Estudiantes",
        "grades_heading": "Estudiantes por grado",
        "groups_heading": "Estudiantes por grupo",
        "groups_intro": (
            "Estos son los grupos que cuenta el estado, con sus propias categorías. "
            "Un grupo con pocos estudiantes suele retenerse, y por eso tantas de "
            "estas filas lo dicen."
        ),
        "col_figure": "Dato",
        "col_grade": "Grado",
        "col_group": "Grupo",
        "col_this_school": "En esta escuela",
        "col_publishing": "Escuelas que lo publican",
        "col_withholding": "Escuelas que lo retienen",
        "col_nothing": "Escuelas que no publican nada",
        "caption_total": ("Matrícula total en {school} el Día del Censo, {year}."),
        "caption_grades": ("Matrícula por grado en {school} el Día del Censo, {year}."),
        "caption_groups": "{family} en {school} el Día del Censo, {year}.",
        "coverage_note": (
            "Las últimas tres columnas no se refieren a esta escuela. Cuentan las "
            "{schools} escuelas activas que Homeroom tiene, para que una fila vacía "
            "aquí pueda leerse frente a la frecuencia con la que el estado publica "
            "ese dato."
        ),
        "coverage_heading": "Cuánto de esto publica el estado",
        "coverage_body": (
            "La cobertura se publica junto a los datos a propósito. Una página que "
            "mostrara solo lo que existe parecería un panorama completo, y no lo es."
        ),
        "coverage_schools": "Escuelas activas en esta compilación",
        "coverage_total_published": "Escuelas que publican una matrícula total",
        "coverage_total_withheld": "Escuelas donde ese total está retenido",
        "coverage_total_nothing": "Escuelas que no publican ningún total",
        "coverage_unjoined": "Registros de matrícula sin escuela activa que coincida",
        "not_yet_heading": "Lo que todavía no está en esta página",
        "not_yet_assignments": (
            "Los datos sobre la asignación de maestros todavía no se han obtenido. "
            "California publica, por escuela, cuántas asignaciones docentes estaban "
            "a cargo de un maestro con credencial vigente que corresponde a lo que "
            "enseña. Homeroom puede leer ese archivo y no lo ha conseguido, así que "
            "esta página no muestra ningún dato sobre los maestros de esta escuela y "
            "no lo hará hasta tener el archivo."
        ),
        "not_yet_context": (
            "Las cifras del distrito y del estado todavía no acompañan a cada dato. "
            "Mientras tanto, las columnas de cobertura son el único contexto aquí."
        ),
        "not_yet_measures": (
            "El ausentismo crónico, los indicadores del panel estatal y el gasto por "
            "estudiante tampoco están todavía. Cada uno llega con su propio archivo "
            "y su propia fecha de descarga, o no llega."
        ),
        "sources_heading": "De dónde salen estas cifras",
        "sources_body": (
            "Cada dato de arriba se copió de uno de estos archivos. Nada se estimó, "
            "se promedió ni se completó a partir de una cifra vecina."
        ),
        "source_d1_name": "Nombres de escuelas y distritos",
        "source_d1_title": "Directorio de escuelas y distritos públicos",
        "source_d2_name": "Matrícula",
        "source_d2_title": "Datos de matrícula del Día del Censo",
        "source_file": "Archivo",
        "source_downloaded": "Descargado el",
        "source_year": "Ciclo escolar",
        "source_page": "La página del estado para este archivo",
        "source_fixture": (
            "Archivo de prueba, no un archivo obtenido. Sin fecha de descarga, "
            "porque nadie descargó nada."
        ),
        "footer_unaffiliated": (
            "Homeroom no está afiliado, respaldado ni vinculado al Departamento de "
            "Educación de California, al Estado de California ni a ningún distrito "
            "escolar."
        ),
        "footer_no_ranking": (
            "Sin puntaje, sin calificación, sin clasificación. Si un dato no se "
            "puede mostrar con honestidad, no se muestra."
        ),
    },
}
"""Every user-visible string that is not a data-driven display name."""

GRADE_NAMES: dict[Locale, dict[str, str]] = {
    "en": {
        "GR_TK": "Transitional kindergarten (TK)",
        "GR_KN": "Kindergarten",
        "GR_01": "Grade 1",
        "GR_02": "Grade 2",
        "GR_03": "Grade 3",
        "GR_04": "Grade 4",
        "GR_05": "Grade 5",
        "GR_06": "Grade 6",
        "GR_07": "Grade 7",
        "GR_08": "Grade 8",
        "GR_09": "Grade 9",
        "GR_10": "Grade 10",
        "GR_11": "Grade 11",
        "GR_12": "Grade 12",
    },
    "es": {
        "GR_TK": "Kínder de transición (TK)",
        "GR_KN": "Kínder",
        "GR_01": "Grado 1",
        "GR_02": "Grado 2",
        "GR_03": "Grado 3",
        "GR_04": "Grado 4",
        "GR_05": "Grado 5",
        "GR_06": "Grado 6",
        "GR_07": "Grado 7",
        "GR_08": "Grado 8",
        "GR_09": "Grado 9",
        "GR_10": "Grado 10",
        "GR_11": "Grado 11",
        "GR_12": "Grado 12",
    },
}
"""Grade column codes as a family reads them. Keys mirror
:data:`homeroom.enrollment.GRADE_COLUMNS`, checked by the parity gate."""

FAMILY_NAMES: dict[Locale, dict[str, str]] = {
    "en": {
        "race_ethnicity": "Race and ethnicity",
        "gender": "Gender",
        "english_language_acquisition": "English language acquisition",
        "student_groups": "Student groups",
    },
    "es": {
        "race_ethnicity": "Raza y etnia",
        "gender": "Género",
        "english_language_acquisition": "Adquisición del idioma inglés",
        "student_groups": "Grupos de estudiantes",
    },
}
"""Subgroup family names. Keys mirror
:data:`homeroom.profiles.SUBGROUP_FAMILIES`, checked by the parity gate."""

CATEGORY_NAMES_ES: dict[str, str] = {
    "TA": "Todos los estudiantes",
    # Race and ethnicity. CDE's own label for RE_D is "Not Reported"; expanded in
    # both languages so it cannot be mistaken for the not-reported measure status.
    "RE_A": "Asiático",
    "RE_B": "Afroamericano",
    "RE_D": "Raza o etnia no informada",
    "RE_F": "Filipino",
    "RE_H": "Hispano o latino",
    "RE_I": "Indígena estadounidense o nativo de Alaska",
    "RE_P": "Isleño del Pacífico",
    "RE_T": "Dos o más razas",
    "RE_W": "Blanco",
    # Gender.
    "GN_F": "Femenino",
    "GN_M": "Masculino",
    "GN_X": "No binario",
    # English language acquisition status. ELAS_MISS is expanded for the same
    # reason as RE_D.
    "ELAS_ADEL": "Estudiante adulto del idioma inglés",
    "ELAS_EL": "Estudiante del idioma inglés",
    "ELAS_EO": "Solo inglés",
    "ELAS_IFEP": "Competente en inglés desde el inicio",
    "ELAS_MISS": "Falta el estado de adquisición del idioma inglés",
    "ELAS_RFEP": "Reclasificado como competente en inglés",
    "ELAS_TBD": "Por determinar",
    # Student groups.
    "SG_DS": "Estudiantes con discapacidades",
    "SG_EL": "Estudiantes del idioma inglés",
    "SG_FS": "Jóvenes en hogares de crianza temporal",
    "SG_HM": "Jóvenes sin hogar",
    "SG_MG": "Jóvenes migrantes",
    "SG_SD": "En desventaja socioeconómica",
    # Age ranges: carried so the catalogs stay in step with the pipeline, though
    # profiles do not render them as subgroups.
    "AR_03": "De 0 a 3 años",
    "AR_0418": "De 4 a 18 años",
    "AR_1922": "De 19 a 22 años",
    "AR_2329": "De 23 a 29 años",
    "AR_3039": "De 30 a 39 años",
    "AR_4049": "De 40 a 49 años",
    "AR_50P": "De 50 años en adelante",
}
"""Spanish for every reporting category the pipeline recognizes.

The English side is :data:`homeroom.profiles.CATEGORY_NAMES`, which the build
already refuses to run without. The parity gate asserts the two key sets match, so
a category added upstream cannot reach a Spanish page as an English label.
"""

CATEGORY_NAMES_BY_LOCALE: dict[Locale, dict[str, str]] = {
    "en": dict(CATEGORY_NAMES),
    "es": CATEGORY_NAMES_ES,
}

DELIBERATELY_SHARED: frozenset[str] = frozenset({"site_name", "RE_F"})
"""Strings that are correctly identical in both languages, each for a reason.

``site_name`` is the project's name, a proper noun. ``RE_F`` is CDE's Filipino
category, which is the same word in Spanish. Everything else differing by locale
is enforced; this set is kept short and is itself size-checked by the parity gate,
so it cannot become somewhere to park an untranslated string.
"""

PLURAL_SAFE_CATALOGS: tuple[dict[Locale, dict[str, str]], ...] = (
    UI,
    GRADE_NAMES,
    FAMILY_NAMES,
    CATEGORY_NAMES_BY_LOCALE,
)
"""Every locale-keyed catalog, so the parity gate cannot miss one by being added
to the module and not to the test."""


def strings(locale: Locale) -> dict[str, str]:
    """The UI catalog for one locale."""
    return UI[locale]


def text(locale: Locale, key: str) -> str:
    """One UI string. A missing key raises rather than falling back to English."""
    return UI[locale][key]


def grade_name(locale: Locale, code: str) -> str:
    return GRADE_NAMES[locale][code]


def family_name(locale: Locale, family: str) -> str:
    return FAMILY_NAMES[locale][family]


def category_name(locale: Locale, code: str) -> str:
    return CATEGORY_NAMES_BY_LOCALE[locale][code]


def format_number(value: float) -> str:
    """A count as both locales write it.

    Spanish as written in California, like English, groups thousands with a comma;
    that is the convention CDE's own Spanish materials and the state's Spanish
    ballot and school notices use, so one formatter serves both pages. If a locale
    that groups differently is ever added, this is the single place it changes.
    """
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


__all__ = [
    "CATEGORY_NAMES_BY_LOCALE",
    "CATEGORY_NAMES_ES",
    "DELIBERATELY_SHARED",
    "FAMILY_NAMES",
    "GRADE_COLUMNS",
    "GRADE_NAMES",
    "LOCALES",
    "LOCALE_NAMES",
    "OTHER_LOCALE",
    "PLURAL_SAFE_CATALOGS",
    "SUBGROUP_FAMILIES",
    "UI",
    "Locale",
    "category_name",
    "cde_text_lang",
    "family_name",
    "format_number",
    "grade_name",
    "strings",
    "text",
]
