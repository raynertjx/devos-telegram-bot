import re

LOG_GROUP_ID = -5250672666
LOG_CHAT_ID = LOG_GROUP_ID
TO_IGNORE_CHAT_IDS = {LOG_GROUP_ID}

DISCLAIMER_TEXT = (
    "⚠️ *DISCLAIMER*\n\n"
    "This Telegram bot was developed to make accessing these "
    "daily devotionals more convenient for everyone\\.\n\n"
    "The content is referenced from the digital PDF available on the "
    "*Lighthouse Evangelism* "
    "[website](https://lighthouse\\.org\\.sg/devotional\\-volume\\-1/)\\. "
    "Please note that I have *NOT MODIFIED* the devotional content in any way whatsoever\\.\n\n"
    "If you have any feedback or find any issues with the bot\\, feel free to use the "
    "/feedback command\\. I'd love to hear from you\\!\n\n"
    "_This bot is a personal project and is not an official publication of Lighthouse Evangelism\\._"
)

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

BIBLE_MAP = {
    "Genesis": "GEN",
    "Exodus": "EXO",
    "Leviticus": "LEV",
    "Numbers": "NUM",
    "Deuteronomy": "DEU",
    "Joshua": "JOS",
    "Judges": "JDG",
    "Ruth": "RUT",
    "1 Samuel": "1SA",
    "2 Samuel": "2SA",
    "1 Kings": "1KI",
    "2 Kings": "2KI",
    "1 Chronicles": "1CH",
    "2 Chronicles": "2CH",
    "Ezra": "EZR",
    "Nehemiah": "NEH",
    "Esther": "EST",
    "Job": "JOB",
    "Psalms": "PSA",
    "Psalm": "PSA",
    "Proverbs": "PRO",
    "Ecclesiastes": "ECC",
    "Song of Solomon": "SNG",
    "Song of Songs": "SNG",
    "Isaiah": "ISA",
    "Jeremiah": "JER",
    "Lamentations": "LAM",
    "Ezekiel": "EZK",
    "Daniel": "DAN",
    "Hosea": "HOS",
    "Joel": "JOL",
    "Amos": "AMO",
    "Obadiah": "OBA",
    "Jonah": "JON",
    "Micah": "MIC",
    "Nahum": "NAM",
    "Habakkuk": "HAB",
    "Zephaniah": "ZEP",
    "Haggai": "HAG",
    "Zechariah": "ZEC",
    "Malachi": "MAL",
    "Matthew": "MAT",
    "Mark": "MRK",
    "Luke": "LUK",
    "John": "JHN",
    "Acts": "ACT",
    "Romans": "ROM",
    "1 Corinthians": "1CO",
    "2 Corinthians": "2CO",
    "Galatians": "GAL",
    "Ephesians": "EPH",
    "Philippians": "PHP",
    "Colossians": "COL",
    "1 Thessalonians": "1TH",
    "2 Thessalonians": "2TH",
    "1 Timothy": "1TI",
    "2 Timothy": "2TI",
    "Titus": "TIT",
    "Philemon": "PHM",
    "Hebrews": "HEB",
    "James": "JAS",
    "1 Peter": "1PE",
    "2 Peter": "2PE",
    "1 John": "1JN",
    "2 John": "2JN",
    "3 John": "3JN",
    "Jude": "JUD",
    "Revelation": "REV",
}

BIBLE_VERSIONS = {
    "NIV": 111,
    "ESV": 59,
    "KJV": 1,
    "NKJV": 114,
    "NASB": 100,
    "NLT": 116,
    "AMP": 1588,
}

VERSION_ID_TO_CODE = {version_id: code for code, version_id in BIBLE_VERSIONS.items()}

DATE_RE = re.compile(
    rf"^(?:{'|'.join(MONTHS)})\s+\d{{1,2}}(?:,\s*\d{{4}})?",
    re.MULTILINE,
)
