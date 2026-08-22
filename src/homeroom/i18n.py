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
from homeroom.profiles import (
    ABSENTEEISM_CATEGORY_NAMES,
    CATEGORY_NAMES,
    SUBGROUP_FAMILIES,
)

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
        "context_body": (
            "Beside each figure are the same figures for this school's district and "
            "for California. They are there to give a number a size, not to award a "
            "verdict: being above or below either one is not by itself good or bad. "
            "Both come from the state's own district and statewide rows in the same "
            "file. Homeroom does not add schools together to make them, because any "
            "such total would quietly leave out the students whose numbers the state "
            "withheld."
        ),
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
        "col_district": "In this district",
        "col_state": "In California",
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
        "absenteeism_heading": "Chronic absenteeism",
        "absenteeism_intro": (
            "A student is chronically absent if they missed 10% or more of the "
            "days they were expected to attend. The rate below is the state's own "
            "figure, counted only from students eligible to be considered: a "
            "student enrolled too briefly, or exempt for reasons the state sets, "
            "is not part of it. Homeroom does not compute this rate; it is printed "
            "exactly as the state published it."
        ),
        "caption_absenteeism_total": (
            "Chronic absenteeism at {school}, {year} school year."
        ),
        "caption_absenteeism_groups": (
            "{family} chronic absenteeism at {school}, {year} school year."
        ),
        "coverage_absenteeism_published": (
            "Schools publishing a chronic absenteeism rate"
        ),
        "coverage_absenteeism_withheld": "Schools where that rate is withheld",
        "coverage_absenteeism_nothing": (
            "Schools publishing no chronic absenteeism rate at all"
        ),
        "not_yet_heading": "What is not on this page yet",
        "not_yet_assignments": (
            "Teacher assignment data is not yet published here. California "
            "publishes, for each school, how many teaching assignments were held "
            "by a teacher with a clear credential matched to what they teach. "
            "Homeroom has read that file and confirmed what it contains, and has "
            "not yet decided how to publish it, so this page shows no figure about "
            "the teachers at this school."
        ),
        "not_yet_absenteeism": (
            "Chronic absenteeism data is not yet acquired for this page. Homeroom "
            "can read that file and has not obtained it here, so this page shows "
            "no chronic-absenteeism figure and will not until the file is in hand."
        ),
        "not_yet_measures": (
            "The state dashboard indicators and per-pupil spending are not here "
            "yet either. Each one arrives with its own file and its own access "
            "date, or it does not arrive."
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
        "source_d3_name": "Chronic absenteeism",
        "source_d3_title": "Chronic Absenteeism Data",
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
        # The ask layer (ADR 0003). Fixed strings the model never writes: the
        # labels around its output and every refusal.
        "ask_label_ai": (
            "Written by an AI model from this school's published figures. "
            "Unofficial. Not a ranking, not a recommendation, and not reviewed "
            "by a person. Every sentence shown was checked against the published "
            "data; sentences that could not be checked were withheld."
        ),
        "ask_label_language": (
            "The model wrote this answer in English. It has not been reviewed."
        ),
        "ask_withheld_count": (
            "Sentences withheld because they could not be verified against the "
            "published data: {count}"
        ),
        "ask_empty_answer": (
            "Nothing the model wrote could be verified against the published "
            "data, so nothing is shown. The tables on this school's page are "
            "complete without it."
        ),
        "ask_intro_measures": (
            "What the published data says, each figure on its own terms:"
        ),
        "ask_intro_definition": "In the California Department of Education's own words:",
        "ask_refusal_judgment": (
            "Homeroom does not rank schools, grade them, score them, or say "
            "whether one is better than another, and neither does this answer. "
            "A single judgment about a school hides more than it shows and "
            "tends to track the wealth of the families it serves rather than "
            "anything the school controls. What the state actually publishes "
            "about this school is below, each figure on its own terms, beside "
            "the district and statewide figures the page already shows."
        ),
        "ask_refusal_outside": (
            "That is not something the California Department of Education's "
            "published files say about this school, so this answer cannot say "
            "it either. The files behind this page cover enrollment on Census "
            "Day and chronic absenteeism. Anything else, such as teaching "
            "quality, safety, or how a school feels, is a question for the "
            "school itself."
        ),
        "ask_refusal_unknown_school": (
            "This build carries no active school with that CDS code, so there "
            "is nothing to answer from. The school may have closed, may not be "
            "in the directory file this build was made from, or the code may "
            "be mistyped."
        ),
        "ask_refusal_unclear": (
            "It is not clear which published figure the question is about. "
            "You can ask about total enrollment, enrollment by grade or by "
            "student group, chronic absenteeism overall or by student group, "
            "how a figure compares with the district or the state, or what a "
            "measure means and how it is calculated."
        ),
        "ask_refusal_nothing_published": (
            "The state published nothing for this school on the figures the "
            "question is about, so there is no number to report. Where a "
            "figure was withheld to protect privacy, that is said below; "
            "where the file never mentions this school, that is said too."
        ),
        "ask_refusal_unavailable": (
            "The answering service is not available right now. The tables on "
            "this school's page are complete without it."
        ),
        "ask_refusal_rate_limited": (
            "Too many questions right now. Try again in a minute; the tables on "
            "this school's page are complete without it."
        ),
        "ask_refusal_cap_reached": (
            "The answering service has reached its daily limit. It will be back "
            "tomorrow; the tables on this school's page are complete without it."
        ),
        "ask_source_prefix": "Source",
        "ask_quote_prefix": "Quoted from",
        # The ask page itself (the opt-in). Still fixed strings.
        "ask_link": "Ask a question about this school (AI, unofficial)",
        "ask_page_eyebrow": "Ask about a school",
        "ask_page_title": "Ask about {school}",
        "ask_page_heading": "Ask about",
        "ask_page_back": "Back to this school's page, which is complete without this",
        "ask_page_label_title": "What this is.",
        "ask_page_intro": (
            "Type a question about this school's published figures, in English "
            "or Spanish. A model reads only what this school's page already "
            "shows, answers in short sentences, and every sentence is checked "
            "against the published data before it is shown. Nothing you type "
            "is stored."
        ),
        "ask_page_label_question": "Your question",
        "ask_page_button": "Ask",
        "ask_page_noscript": (
            "Sending a question needs JavaScript, which this browser has turned "
            "off. The school page, linked above, is complete without it."
        ),
        "ask_page_answer_heading": "Answer",
        "ask_page_sending": "Asking...",
        "ask_page_citations": "Checked against",
        "ask_page_on_page": "on this school's page",
        "ask_page_cde_page": "CDE page",
        "ask_page_model": "Model",
        "ask_page_fixture": "(test data, not a real school)",
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
        "context_body": (
            "Junto a cada dato aparecen las mismas cifras del distrito de esta "
            "escuela y de California. Están ahí para dar tamaño a un número, no para "
            "emitir un juicio: estar por encima o por debajo de cualquiera de ellas "
            "no es en sí mismo bueno ni malo. Ambas provienen de las filas de "
            "distrito y de estado que el estado publica en el mismo archivo. Homeroom "
            "no suma escuelas para obtenerlas, porque cualquier total así dejaría "
            "fuera en silencio a los estudiantes cuyas cifras el estado retuvo."
        ),
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
        "col_district": "En este distrito",
        "col_state": "En California",
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
        "absenteeism_heading": "Ausentismo crónico",
        "absenteeism_intro": (
            "Un estudiante tiene ausentismo crónico si faltó el 10% o más de los "
            "días en que se esperaba que asistiera. La tasa de abajo es la cifra "
            "propia del estado, contada solo entre los estudiantes elegibles para "
            "considerarse: un estudiante matriculado muy poco tiempo, o exento por "
            "razones que fija el estado, no forma parte de ella. Homeroom no "
            "calcula esta tasa; se muestra tal como la publicó el estado."
        ),
        "caption_absenteeism_total": (
            "Ausentismo crónico en {school}, ciclo escolar {year}."
        ),
        "caption_absenteeism_groups": (
            "Ausentismo crónico de {family} en {school}, ciclo escolar {year}."
        ),
        "coverage_absenteeism_published": (
            "Escuelas que publican una tasa de ausentismo crónico"
        ),
        "coverage_absenteeism_withheld": "Escuelas donde esa tasa está retenida",
        "coverage_absenteeism_nothing": (
            "Escuelas que no publican ninguna tasa de ausentismo crónico"
        ),
        "not_yet_heading": "Lo que todavía no está en esta página",
        "not_yet_assignments": (
            "Los datos sobre la asignación de maestros todavía no se publican "
            "aquí. California publica, por escuela, cuántas asignaciones docentes "
            "estaban a cargo de un maestro con credencial vigente que corresponde "
            "a lo que enseña. Homeroom leyó ese archivo y confirmó lo que "
            "contiene, y todavía no ha decidido cómo publicarlo, así que esta "
            "página no muestra ningún dato sobre los maestros de esta escuela."
        ),
        "not_yet_absenteeism": (
            "Los datos de ausentismo crónico todavía no se han obtenido para esta "
            "página. Homeroom puede leer ese archivo y no lo ha conseguido aquí, "
            "así que esta página no muestra ningún dato de ausentismo crónico y no "
            "lo hará hasta tener el archivo."
        ),
        "not_yet_measures": (
            "Los indicadores del panel estatal y el gasto por estudiante tampoco "
            "están todavía. Cada uno llega con su propio archivo y su propia fecha "
            "de descarga, o no llega."
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
        "source_d3_name": "Ausentismo crónico",
        "source_d3_title": "Datos de ausentismo crónico",
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
        # La capa de preguntas (ADR 0003). Cadenas fijas que el modelo nunca
        # escribe: las etiquetas alrededor de su respuesta y cada negativa.
        "ask_label_ai": (
            "Escrito por un modelo de inteligencia artificial a partir de las "
            "cifras publicadas de esta escuela. No oficial. No es una "
            "clasificación, no es una recomendación y no fue revisado por una "
            "persona. Cada oración que se muestra fue verificada contra los "
            "datos publicados; las que no se pudieron verificar se retuvieron."
        ),
        "ask_label_language": (
            "El modelo escribió esta respuesta en español. Es una traducción "
            "automática y no ha sido revisada por una persona."
        ),
        "ask_withheld_count": (
            "Oraciones retenidas porque no se pudieron verificar contra los "
            "datos publicados: {count}"
        ),
        "ask_empty_answer": (
            "Nada de lo que escribió el modelo se pudo verificar contra los "
            "datos publicados, así que no se muestra nada. Las tablas de la "
            "página de esta escuela están completas sin esta respuesta."
        ),
        "ask_intro_measures": (
            "Lo que dicen los datos publicados, cada cifra en sus propios términos:"
        ),
        "ask_intro_definition": (
            "En las propias palabras del Departamento de Educación de California:"
        ),
        "ask_refusal_judgment": (
            "Homeroom no clasifica escuelas, no les pone calificación ni puntaje, "
            "ni dice si una es mejor que otra, y esta respuesta tampoco. Un "
            "solo juicio sobre una escuela oculta más de lo que muestra y suele "
            "reflejar la riqueza de las familias a las que sirve más que "
            "cualquier cosa que la escuela controle. Lo que el estado realmente "
            "publica sobre esta escuela está abajo, cada cifra en sus propios "
            "términos, junto a las cifras del distrito y del estado que la "
            "página ya muestra."
        ),
        "ask_refusal_outside": (
            "Eso no es algo que los archivos publicados del Departamento de "
            "Educación de California digan sobre esta escuela, así que esta "
            "respuesta tampoco puede decirlo. Los archivos detrás de esta "
            "página cubren la matrícula del Día del Censo y el ausentismo "
            "crónico. Cualquier otra cosa, como la calidad de la enseñanza, la "
            "seguridad o cómo se siente una escuela, es una pregunta para la "
            "escuela misma."
        ),
        "ask_refusal_unknown_school": (
            "Esta versión no incluye ninguna escuela activa con ese código CDS, "
            "así que no hay nada de dónde responder. Puede que la escuela haya "
            "cerrado, que no esté en el archivo del directorio con el que se "
            "hizo esta versión, o que el código esté mal escrito."
        ),
        "ask_refusal_unclear": (
            "No queda claro a qué cifra publicada se refiere la pregunta. Puede "
            "preguntar por la matrícula total, la matrícula por grado o por "
            "grupo de estudiantes, el ausentismo crónico en general o por grupo "
            "de estudiantes, cómo se compara una cifra con el distrito o con el "
            "estado, o qué significa una medida y cómo se calcula."
        ),
        "ask_refusal_nothing_published": (
            "El estado no publicó nada sobre esta escuela para las cifras a las "
            "que se refiere la pregunta, así que no hay ningún número que "
            "informar. Donde una cifra se retuvo para proteger la privacidad, "
            "se dice abajo; donde el archivo nunca menciona a esta escuela, "
            "también se dice."
        ),
        "ask_refusal_unavailable": (
            "El servicio de respuestas no está disponible en este momento. Las "
            "tablas de la página de esta escuela están completas sin él."
        ),
        "ask_refusal_rate_limited": (
            "Demasiadas preguntas en este momento. Inténtelo de nuevo en un "
            "minuto; las tablas de la página de esta escuela están completas "
            "sin esta respuesta."
        ),
        "ask_refusal_cap_reached": (
            "El servicio de respuestas alcanzó su límite diario. Volverá "
            "mañana; las tablas de la página de esta escuela están completas "
            "sin él."
        ),
        "ask_source_prefix": "Fuente",
        "ask_quote_prefix": "Citado de",
        # La página de preguntas (la opción voluntaria). Siguen siendo cadenas fijas.
        "ask_link": "Haga una pregunta sobre esta escuela (IA, no oficial)",
        "ask_page_eyebrow": "Preguntar sobre una escuela",
        "ask_page_title": "Preguntar sobre {school}",
        "ask_page_heading": "Preguntar sobre",
        "ask_page_back": (
            "Volver a la página de esta escuela, que está completa sin esto"
        ),
        "ask_page_label_title": "Qué es esto.",
        "ask_page_intro": (
            "Escriba una pregunta sobre las cifras publicadas de esta escuela, en "
            "español o en inglés. Un modelo lee solo lo que la página de esta "
            "escuela ya muestra, responde en oraciones cortas, y cada oración se "
            "verifica contra los datos publicados antes de mostrarse. Nada de lo "
            "que escriba se guarda."
        ),
        "ask_page_label_question": "Su pregunta",
        "ask_page_button": "Preguntar",
        "ask_page_noscript": (
            "Para enviar una pregunta se necesita JavaScript, que este navegador "
            "tiene desactivado. La página de la escuela, enlazada arriba, está "
            "completa sin esto."
        ),
        "ask_page_answer_heading": "Respuesta",
        "ask_page_sending": "Preguntando...",
        "ask_page_citations": "Verificado contra",
        "ask_page_on_page": "en la página de esta escuela",
        "ask_page_cde_page": "página del CDE",
        "ask_page_model": "Modelo",
        "ask_page_fixture": "(datos de prueba, no una escuela real)",
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

ABSENTEEISM_CATEGORY_NAMES_ES: dict[str, str] = {
    "TA": "Todos los estudiantes",
    # Race and ethnicity. CDE's own label for RD is "Did not Report"; expanded in
    # both languages for the same reason D2's RE_D is.
    "RA": "Asiático",
    "RB": "Afroamericano",
    "RD": "Raza o etnia no informada",
    "RF": "Filipino",
    "RH": "Hispano o latino",
    "RI": "Indígena estadounidense o nativo de Alaska",
    "RP": "Isleño del Pacífico",
    "RT": "Dos o más razas",
    "RW": "Blanco",
    # Gender.
    "GF": "Femenino",
    "GM": "Masculino",
    "GX": "No binario",
    # Student groups.
    "SD": "Estudiantes con discapacidades",
    "SE": "Estudiantes del idioma inglés",
    "SF": "Jóvenes en hogares de crianza temporal",
    "SH": "Jóvenes sin hogar",
    "SM": "Jóvenes migrantes",
    "SS": "En desventaja socioeconómica",
    # Grade spans: carried so the catalogs stay in step with the pipeline, though
    # profiles do not render them as a subgroup family.
    "GRTKKN": "Grados TK a kínder",
    "GR13": "Grados 1 a 3",
    "GR46": "Grados 4 a 6",
    "GR78": "Grados 7 y 8",
    "GRTK8": "Grados TK/kínder a 8",
    "GR912": "Grados 9 a 12",
}
"""Spanish for every D3 reporting-category code this pipeline recognizes. The
English side is :data:`homeroom.profiles.ABSENTEEISM_CATEGORY_NAMES`, which the
build already refuses to run without. The parity gate asserts the two key sets
match, the same guarantee :data:`CATEGORY_NAMES_ES` gives D2's codes."""

ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE: dict[Locale, dict[str, str]] = {
    "en": dict(ABSENTEEISM_CATEGORY_NAMES),
    "es": ABSENTEEISM_CATEGORY_NAMES_ES,
}

DELIBERATELY_SHARED: frozenset[str] = frozenset({"site_name", "RE_F", "RF"})
"""Strings that are correctly identical in both languages, each for a reason.

``site_name`` is the project's name, a proper noun. ``RE_F`` (D2) and ``RF`` (D3)
are CDE's two different codes for the same Filipino category, each the same word
in Spanish. Everything else differing by locale is enforced; this set is kept
short and is itself size-checked by the parity gate, so it cannot become somewhere
to park an untranslated string.

D2's and D3's ``CATEGORY_NAMES`` catalogs both use the key ``TA`` (D2's own
"All students"/"Todos los estudiantes"; D3's own, separately translated pair for
the same key), which is not a parity concern: :data:`PLURAL_SAFE_CATALOGS` checks
each catalog's English and Spanish values against each other, never one catalog's
values against another's, so the two ``TA`` entries are independent strings that
each already differ correctly between locales.
"""

PLURAL_SAFE_CATALOGS: tuple[dict[Locale, dict[str, str]], ...] = (
    UI,
    GRADE_NAMES,
    FAMILY_NAMES,
    CATEGORY_NAMES_BY_LOCALE,
    ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE,
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


def absenteeism_category_name(locale: Locale, code: str) -> str:
    return ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE[locale][code]


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
    "ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE",
    "ABSENTEEISM_CATEGORY_NAMES_ES",
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
    "absenteeism_category_name",
    "category_name",
    "cde_text_lang",
    "family_name",
    "format_number",
    "grade_name",
    "strings",
    "text",
]
