"""
bible_shorts/content.py — Bible verse database and content provider.

Organised by category for easy theme-based selection. Each verse entry includes
the reference, text, and metadata for rendering.

Adding a new verse requires ONLY a new entry in the VERSES dictionary.
Adding a new category requires a new key + entries.
"""

import random
from dataclasses import dataclass, field
from typing import Optional

from bible_shorts import config as cfg


@dataclass
class BibleVerse:
    """A single Bible verse entry ready for narration and rendering."""
    reference: str          # e.g. "Psalm 23:1"
    book: str               # e.g. "Psalm"
    chapter: int
    verse: int
    text: str               # The Scripture text
    translation: str = "ESV"  # Bible translation
    category: str = ""      # Primary category
    tags: list[str] = field(default_factory=list)  # Additional tags
    theme_background: str = ""  # Suggested background type


# ── Hook templates by category ──────────────────────────────────────────────

HOOKS_BY_CATEGORY = {
    "peace": [
        "Feeling overwhelmed today?",
        "Need peace right now?",
        "Let this truth calm your heart.",
        "When your mind won't be quiet...",
        "Read this slowly.",
        "If you're restless today...",
        "This is what peace feels like.",
        "Close your eyes for a moment. Now listen.",
    ],
    "hope": [
        "This verse has comforted millions.",
        "If you're losing hope today...",
        "There is always a reason to hold on.",
        "When life feels impossible...",
        "This changed everything for me.",
        "A promise that never fails.",
        "For anyone who needs light today.",
        "Hope is closer than you think.",
    ],
    "strength": [
        "Feeling weak today?",
        "You are stronger than you know.",
        "When you have nothing left...",
        "This is for the weary.",
        "Strength isn't about never falling.",
        "God wants you to hear this.",
        "For anyone carrying a heavy burden.",
        "You weren't meant to carry this alone.",
    ],
    "faith": [
        "This verse changed everything.",
        "What if you chose to trust today?",
        "Faith isn't about having all the answers.",
        "When doubt creeps in...",
        "This is what faith looks like.",
        "For anyone questioning right now.",
        "Trust the process. Trust Him.",
        "Faith this small can move mountains.",
    ],
    "love": [
        "You are deeply loved.",
        "This is the greatest truth.",
        "God wants you to know this.",
        "There is no greater love.",
        "Read this and let it sink in.",
        "This is for anyone feeling unloved.",
        "Love never fails.",
        "You were loved before you took your first breath.",
    ],
    "wisdom": [
        "Ancient words. Timeless truth.",
        "This will change how you see things.",
        "Wisdom speaks softly. Listen.",
        "One verse. Infinite depth.",
        "The smartest thing you'll hear today.",
        "Solomon understood something we forget.",
        "True wisdom starts here.",
    ],
    "encouragement": [
        "This is for anyone feeling alone.",
        "You need to hear this today.",
        "Keep going. You're almost there.",
        "Don't give up just yet.",
        "God hasn't forgotten you.",
        "This is your sign to keep believing.",
        "Someone prayed for you today.",
    ],
    "forgiveness": [
        "Is there something you need to let go of?",
        "Forgiveness is hard. But freedom is harder to live without.",
        "You don't have to carry this anymore.",
        "This truth sets people free.",
        "The weight you're carrying... you can put it down.",
    ],
    "anxiety": [
        "If you're anxious today...",
        "Breathe. Read this slowly.",
        "Your worry does not define you.",
        "Cast your cares on Him.",
        "Anxiety doesn't get the final word.",
        "This verse is for anxious hearts.",
        "You are held, even when you don't feel it.",
    ],
    "psalms": [
        "The Psalms have comforted hearts for thousands of years.",
        "David poured out his soul. Listen.",
        "This Psalm speaks what your heart feels.",
        "Ancient poetry. Present comfort.",
        "When words fail, the Psalms speak.",
    ],
    "proverbs": [
        "Wisdom that has stood the test of time.",
        "One proverb can change your day.",
        "Solomon's words still ring true.",
        "Practical wisdom. Timeless truth.",
    ],
    "gospel": [
        "Jesus spoke these words.",
        "The most important truth you'll hear today.",
        "These words changed the world.",
        "Listen to what Jesus said.",
        "The Gospel in one verse.",
    ],
    "hardship": [
        "Going through a hard season?",
        "This is for anyone in the valley.",
        "The fire refines. It doesn't destroy.",
        "Your struggle has purpose.",
        "This too shall pass. But until then...",
    ],
    "default": [
        "Read this slowly.",
        "Let this sink in.",
        "Your daily Scripture.",
        "Take a moment with this.",
        "God's Word for you today.",
    ],
}


def get_hook(category: str) -> str:
    """Return a random hook appropriate for the verse category."""
    hooks = HOOKS_BY_CATEGORY.get(category, HOOKS_BY_CATEGORY["default"])
    return random.choice(hooks)


# ── Reflection templates ────────────────────────────────────────────────────
# Generated as structured templates that can be AI-expanded in the future.
# For now, these are hand-crafted reflections that stay faithful to Scripture.

REFLECTIONS = {
    "peace": [
        "His peace isn't the absence of trouble — it's the presence of His calm in the middle of it.",
        "Let this truth settle into the quiet places of your heart.",
        "In a world that never stops, He invites you to rest.",
        "Peace isn't something you find. It's Someone you trust.",
    ],
    "hope": [
        "God's promises remain true even when life feels uncertain.",
        "Hope is the anchor that holds steady when everything else shifts.",
        "The God who kept every promise in Scripture is still faithful today.",
        "Your story isn't over. The best chapters may still be ahead.",
    ],
    "strength": [
        "When your strength runs out, His is just beginning.",
        "You don't have to be strong enough. You just have to trust the One who is.",
        "True strength isn't holding it all together — it's knowing Who holds you.",
        "Even on your weakest day, you are carried by infinite strength.",
    ],
    "faith": [
        "Faith doesn't require you to see the whole staircase — just the next step.",
        "Trust isn't about understanding everything. It's about knowing Who is in control.",
        "Even a small seed of faith can grow into something unshakeable.",
        "Your faith, however fragile, is precious to God.",
    ],
    "love": [
        "You are loved more deeply than you could ever comprehend.",
        "His love isn't based on what you do — it's based on Who He is.",
        "Nothing can separate you from His love. Nothing.",
        "Before you ever loved Him, He loved you completely.",
    ],
    "wisdom": [
        "Wisdom isn't about knowing everything. It's about knowing what matters.",
        "The fear of the Lord isn't terror — it's reverence rooted in love.",
        "True wisdom begins when we acknowledge there is Someone greater.",
        "Apply this truth today and watch how it transforms ordinary moments.",
    ],
    "encouragement": [
        "You are seen. You are known. You are not forgotten.",
        "The same God who parted seas and moved mountains is walking with you now.",
        "Your current struggle is not your final chapter.",
        "Keep going. Every step forward, no matter how small, is still progress.",
    ],
    "forgiveness": [
        "Forgiveness doesn't mean what happened was okay — it means you're free.",
        "Letting go isn't weakness. It's choosing peace over poison.",
        "The grace you've received is the grace you can offer.",
        "Freedom begins the moment you release what you've been holding.",
    ],
    "anxiety": [
        "Bring your worries to Him — He can handle what you cannot.",
        "Your anxious thoughts are not the truth. His Word is.",
        "Peace doesn't mean the storm stops. It means you're anchored in the storm.",
        "Take a breath. You are held by hands that hold the universe.",
    ],
    "psalms": [
        "The Psalms remind us that every emotion can be brought before God.",
        "David knew sorrow and joy — and brought both to the Lord honestly.",
        "When you can't find the words to pray, the Psalms give them to you.",
    ],
    "proverbs": [
        "Wisdom isn't just knowledge — it's knowing how to live well.",
        "One wise decision today can shape a lifetime of tomorrows.",
        "These ancient words are as practical now as the day they were written.",
    ],
    "gospel": [
        "The Gospel isn't just good advice — it's good news.",
        "Everything changed when Jesus spoke these words.",
        "This isn't just a teaching. It's an invitation to life.",
    ],
    "hardship": [
        "The darkest valleys often lead to the most beautiful views.",
        "What feels like breaking may actually be remaking.",
        "You are not being punished — you are being prepared.",
        "Hold on. The dawn always follows the darkest hour.",
    ],
    "default": [
        "Let these words take root in your heart today.",
        "God's Word never returns empty. Let it work in you.",
        "Take this truth with you through the rest of your day.",
        "Meditate on this. Let it shape how you see everything.",
    ],
}


def get_reflection(category: str) -> str:
    """Return a reflection appropriate for the verse category."""
    reflections = REFLECTIONS.get(category, REFLECTIONS["default"])
    return random.choice(reflections)


# ── Call to action templates ────────────────────────────────────────────────

CTAS = [
    "Save this for later.",
    "Follow for daily Scripture.",
    "Share this with someone who needs it.",
    "God bless you. See you tomorrow.",
    "Follow along for more daily verses.",
    "Send this to a friend who could use it today.",
    "Save this. Come back to it when you need it.",
    "Follow for more Scripture every day.",
    "Share this if it encouraged you.",
    "God bless you. Rest in His Word.",
]


def get_cta() -> str:
    """Return a random soft call to action."""
    return random.choice(CTAS)


# ── Outro messages ──────────────────────────────────────────────────────────

OUTROS = [
    "God bless you.",
    "Follow for daily Scripture.",
    "See you tomorrow.",
    "Peace be with you.",
    "Stay in the Word.",
    "Grace and peace to you.",
    "Until tomorrow.",
    "Rest in His promises.",
]


def get_outro() -> str:
    """Return a random outro message."""
    return random.choice(OUTROS)


# ── Bible verse database ────────────────────────────────────────────────────
# Each verse is: (reference, text, category, tags, theme_background)
#
# Theme background hints for future auto-matching:
#   sunrise, mountains, forests, rivers, waterfalls, clouds, rain,
#   candlelight, stained_glass, church, manuscripts, fields, ocean,
#   stars, fire, olive_trees, desert, nature, aerial

VERSES = [
    # ═══════════ PEACE ═══════════
    ("John 14:27", "Peace I leave with you; my peace I give to you. Not as the world gives do I give to you. Let not your hearts be troubled, neither let them be afraid.",
     "peace", ["jesus", "comfort"], "candlelight"),
    ("Philippians 4:7", "And the peace of God, which surpasses all understanding, will guard your hearts and your minds in Christ Jesus.",
     "peace", ["comfort", "promise"], "sunrise"),
    ("Isaiah 26:3", "You keep him in perfect peace whose mind is stayed on you, because he trusts in you.",
     "peace", ["trust", "mind"], "forests"),
    ("Psalm 46:10", "Be still, and know that I am God. I will be exalted among the nations, I will be exalted in the earth!",
     "peace", ["stillness", "psalms", "surrender"], "mountains"),
    ("Colossians 3:15", "And let the peace of Christ rule in your hearts, to which indeed you were called in one body. And be thankful.",
     "peace", ["christ", "gratitude"], "fields"),
    ("Psalm 29:11", "May the Lord give strength to his people! May the Lord bless his people with peace!",
     "peace", ["psalms", "blessing"], "ocean"),
    ("Numbers 6:24-26", "The Lord bless you and keep you; the Lord make his face to shine upon you and be gracious to you; the Lord lift up his countenance upon you and give you peace.",
     "peace", ["blessing", "benediction"], "sunrise"),
    ("2 Thessalonians 3:16", "Now may the Lord of peace himself give you peace at all times in every way. The Lord be with you all.",
     "peace", ["blessing", "promise"], "clouds"),

    # ═══════════ HOPE ═══════════
    ("Jeremiah 29:11", "For I know the plans I have for you, declares the Lord, plans for welfare and not for evil, to give you a future and a hope.",
     "hope", ["promise", "future"], "sunrise"),
    ("Romans 15:13", "May the God of hope fill you with all joy and peace in believing, so that by the power of the Holy Spirit you may abound in hope.",
     "hope", ["joy", "spirit"], "sunrise"),
    ("Isaiah 40:31", "But they who wait for the Lord shall renew their strength; they shall mount up with wings like eagles; they shall run and not be weary; they shall walk and not faint.",
     "hope", ["strength", "renewal"], "mountains"),
    ("Psalm 42:11", "Why are you cast down, O my soul, and why are you in turmoil within me? Hope in God; for I shall again praise him, my salvation and my God.",
     "hope", ["psalms", "struggle"], "ocean"),
    ("Lamentations 3:22-23", "The steadfast love of the Lord never ceases; his mercies never come to an end; they are new every morning; great is your faithfulness.",
     "hope", ["love", "mercy", "faithfulness"], "sunrise"),
    ("Romans 8:28", "And we know that for those who love God all things work together for good, for those who are called according to his purpose.",
     "hope", ["purpose", "promise"], "fields"),
    ("Hebrews 10:23", "Let us hold fast the confession of our hope without wavering, for he who promised is faithful.",
     "hope", ["faithfulness", "perseverance"], "mountains"),
    ("Micah 7:7", "But as for me, I will look to the Lord; I will wait for the God of my salvation; my God will hear me.",
     "hope", ["waiting", "trust"], "clouds"),

    # ═══════════ STRENGTH ═══════════
    ("Isaiah 41:10", "Fear not, for I am with you; be not dismayed, for I am your God; I will strengthen you, I will help you, I will uphold you with my righteous right hand.",
     "strength", ["fear", "comfort", "presence"], "mountains"),
    ("Philippians 4:13", "I can do all things through him who strengthens me.",
     "strength", ["empowerment", "christ"], "mountains"),
    ("Psalm 46:1", "God is our refuge and strength, a very present help in trouble.",
     "strength", ["psalms", "refuge", "help"], "mountains"),
    ("Deuteronomy 31:8", "It is the Lord who goes before you. He will be with you; he will not leave you or forsake you. Do not fear or be dismayed.",
     "strength", ["presence", "courage"], "desert"),
    ("Joshua 1:9", "Have I not commanded you? Be strong and courageous. Do not be frightened, and do not be dismayed, for the Lord your God is with you wherever you go.",
     "strength", ["courage", "presence"], "desert"),
    ("2 Corinthians 12:9", "But he said to me, 'My grace is sufficient for you, for my power is made perfect in weakness.' Therefore I will boast all the more gladly of my weaknesses, so that the power of Christ may rest upon me.",
     "strength", ["grace", "weakness"], "candlelight"),
    ("Psalm 73:26", "My flesh and my heart may fail, but God is the strength of my heart and my portion forever.",
     "strength", ["psalms", "eternal"], "sunrise"),
    ("Nehemiah 8:10", "Do not be grieved, for the joy of the Lord is your strength.",
     "strength", ["joy", "encouragement"], "fields"),

    # ═══════════ FAITH ═══════════
    ("Hebrews 11:1", "Now faith is the assurance of things hoped for, the conviction of things not seen.",
     "faith", ["definition", "hope"], "stars"),
    ("Proverbs 3:5-6", "Trust in the Lord with all your heart, and do not lean on your own understanding. In all your ways acknowledge him, and he will make straight your paths.",
     "faith", ["trust", "proverbs", "guidance"], "forests"),
    ("Matthew 17:20", "For truly, I say to you, if you have faith like a grain of mustard seed, you will say to this mountain, 'Move from here to there,' and it will move, and nothing will be impossible for you.",
     "faith", ["gospel", "jesus", "power"], "mountains"),
    ("2 Corinthians 5:7", "For we walk by faith, not by sight.",
     "faith", ["trust", "perspective"], "forests"),
    ("Mark 11:24", "Therefore I tell you, whatever you ask in prayer, believe that you have received it, and it will be yours.",
     "faith", ["gospel", "prayer", "jesus"], "candlelight"),
    ("James 1:6", "But let him ask in faith, with no doubting, for the one who doubts is like a wave of the sea that is driven and tossed by the wind.",
     "faith", ["prayer", "doubt"], "ocean"),
    ("Galatians 2:20", "I have been crucified with Christ. It is no longer I who live, but Christ who lives in me. And the life I now live in the flesh I live by faith in the Son of God, who loved me and gave himself for me.",
     "faith", ["christ", "identity"], "sunrise"),
    ("Psalm 56:3", "When I am afraid, I put my trust in you.",
     "faith", ["psalms", "fear", "trust"], "candlelight"),

    # ═══════════ LOVE ═══════════
    ("1 Corinthians 13:4-7", "Love is patient and kind; love does not envy or boast; it is not arrogant or rude. It does not insist on its own way; it is not irritable or resentful; it does not rejoice at wrongdoing, but rejoices with the truth. Love bears all things, believes all things, hopes all things, endures all things.",
     "love", ["definition", "character"], "candlelight"),
    ("John 3:16", "For God so loved the world, that he gave his only Son, that whoever believes in him should not perish but have eternal life.",
     "love", ["gospel", "salvation", "jesus"], "sunrise"),
    ("Romans 8:38-39", "For I am sure that neither death nor life, nor angels nor rulers, nor things present nor things to come, nor powers, nor height nor depth, nor anything else in all creation, will be able to separate us from the love of God in Christ Jesus our Lord.",
     "love", ["security", "eternal"], "stars"),
    ("1 John 4:19", "We love because he first loved us.",
     "love", ["origin", "grace"], "candlelight"),
    ("Jeremiah 31:3", "The Lord appeared to him from far away. I have loved you with an everlasting love; therefore I have continued my faithfulness to you.",
     "love", ["faithfulness", "eternal"], "sunrise"),
    ("Zephaniah 3:17", "The Lord your God is in your midst, a mighty one who will save; he will rejoice over you with gladness; he will quiet you by his love; he will exult over you with loud singing.",
     "love", ["joy", "presence", "delight"], "fields"),
    ("Ephesians 3:17-19", "So that Christ may dwell in your hearts through faith—that you, being rooted and grounded in love, may have strength to comprehend with all the saints what is the breadth and length and height and depth, and to know the love of Christ that surpasses knowledge, that you may be filled with all the fullness of God.",
     "love", ["christ", "depth"], "ocean"),
    ("1 John 4:16", "So we have come to know and to believe the love that God has for us. God is love, and whoever abides in love abides in God, and God abides in him.",
     "love", ["identity", "abiding"], "candlelight"),

    # ═══════════ WISDOM ═══════════
    ("Proverbs 3:5-6", "Trust in the Lord with all your heart, and do not lean on your own understanding. In all your ways acknowledge him, and he will make straight your paths.",
     "wisdom", ["proverbs", "trust", "guidance"], "forests"),
    ("James 1:5", "If any of you lacks wisdom, let him ask God, who gives generously to all without reproach, and it will be given him.",
     "wisdom", ["prayer", "promise"], "candlelight"),
    ("Proverbs 9:10", "The fear of the Lord is the beginning of wisdom, and the knowledge of the Holy One is insight.",
     "wisdom", ["proverbs", "reverence"], "mountains"),
    ("Proverbs 16:9", "The heart of man plans his way, but the Lord establishes his steps.",
     "wisdom", ["proverbs", "guidance", "sovereignty"], "forests"),
    ("Colossians 2:2-3", "That their hearts may be encouraged, being knit together in love, to reach all the riches of full assurance of understanding and the knowledge of God's mystery, which is Christ, in whom are hidden all the treasures of wisdom and knowledge.",
     "wisdom", ["christ", "mystery"], "manuscripts"),
    ("Proverbs 2:6", "For the Lord gives wisdom; from his mouth come knowledge and understanding.",
     "wisdom", ["proverbs", "source"], "sunrise"),
    ("Ecclesiastes 3:11", "He has made everything beautiful in its time. Also, he has put eternity into man's heart, yet so that he cannot find out what God has done from the beginning to the end.",
     "wisdom", ["time", "eternity", "mystery"], "fields"),
    ("Proverbs 11:2", "When pride comes, then comes disgrace, but with the humble is wisdom.",
     "wisdom", ["proverbs", "humility"], "forests"),

    # ═══════════ ENCOURAGEMENT ═══════════
    ("Isaiah 41:10", "Fear not, for I am with you; be not dismayed, for I am your God; I will strengthen you, I will help you, I will uphold you with my righteous right hand.",
     "encouragement", ["strength", "presence", "fear"], "mountains"),
    ("Deuteronomy 31:8", "It is the Lord who goes before you. He will be with you; he will not leave you or forsake you. Do not fear or be dismayed.",
     "encouragement", ["presence", "courage"], "desert"),
    ("Psalm 34:18", "The Lord is near to the brokenhearted and saves the crushed in spirit.",
     "encouragement", ["psalms", "comfort", "healing"], "candlelight"),
    ("Matthew 11:28", "Come to me, all who labor and are heavy laden, and I will give you rest.",
     "encouragement", ["gospel", "jesus", "rest"], "fields"),
    ("Isaiah 43:2", "When you pass through the waters, I will be with you; and through the rivers, they shall not overwhelm you; when you walk through fire you shall not be burned, and the flame shall not consume you.",
     "encouragement", ["protection", "presence", "trials"], "rivers"),
    ("Psalm 55:22", "Cast your burden on the Lord, and he will sustain you; he will never permit the righteous to be moved.",
     "encouragement", ["psalms", "surrender", "stability"], "mountains"),
    ("Romans 8:31", "What then shall we say to these things? If God is for us, who can be against us?",
     "encouragement", ["victory", "confidence"], "mountains"),
    ("Psalm 121:1-2", "I lift up my eyes to the hills. From where does my help come? My help comes from the Lord, who made heaven and earth.",
     "encouragement", ["psalms", "help", "creator"], "mountains"),

    # ═══════════ FORGIVENESS ═══════════
    ("1 John 1:9", "If we confess our sins, he is faithful and just to forgive us our sins and to cleanse us from all unrighteousness.",
     "forgiveness", ["confession", "cleansing", "faithfulness"], "waterfalls"),
    ("Ephesians 4:32", "Be kind to one another, tenderhearted, forgiving one another, as God in Christ forgave you.",
     "forgiveness", ["kindness", "christ", "example"], "candlelight"),
    ("Psalm 103:12", "As far as the east is from the west, so far does he remove our transgressions from us.",
     "forgiveness", ["psalms", "grace", "freedom"], "sunrise"),
    ("Isaiah 1:18", "Come now, let us reason together, says the Lord: though your sins are like scarlet, they shall be as white as snow; though they are red like crimson, they shall become like wool.",
     "forgiveness", ["cleansing", "grace", "transformation"], "snow"),  # snow = general nature
    ("Micah 7:18-19", "Who is a God like you, pardoning iniquity and passing over transgression for the remnant of his inheritance? He does not retain his anger forever, because he delights in steadfast love. He will again have compassion on us; he will tread our iniquities underfoot. You will cast all our sins into the depths of the sea.",
     "forgiveness", ["mercy", "compassion", "love"], "ocean"),
    ("Matthew 6:14", "For if you forgive others their trespasses, your heavenly Father will also forgive you.",
     "forgiveness", ["gospel", "jesus", "teaching"], "candlelight"),
    ("Colossians 3:13", "Bearing with one another and, if one has a complaint against another, forgiving each other; as the Lord has forgiven you, so you also must forgive.",
     "forgiveness", ["community", "grace"], "forests"),
    ("Luke 23:34", "And Jesus said, 'Father, forgive them, for they know not what they do.'",
     "forgiveness", ["gospel", "jesus", "cross"], "stained_glass"),

    # ═══════════ ANXIETY ═══════════
    ("Philippians 4:6-7", "Do not be anxious about anything, but in everything by prayer and supplication with thanksgiving let your requests be made known to God. And the peace of God, which surpasses all understanding, will guard your hearts and your minds in Christ Jesus.",
     "anxiety", ["peace", "prayer", "gratitude"], "candlelight"),
    ("Matthew 6:34", "Therefore do not be anxious about tomorrow, for tomorrow will be anxious for itself. Sufficient for the day is its own trouble.",
     "anxiety", ["gospel", "jesus", "today"], "sunrise"),
    ("1 Peter 5:7", "Casting all your anxieties on him, because he cares for you.",
     "anxiety", ["surrender", "care"], "fields"),
    ("Psalm 94:19", "When the cares of my heart are many, your consolations cheer my soul.",
     "anxiety", ["psalms", "comfort"], "candlelight"),
    ("Isaiah 35:4", "Say to those who have an anxious heart, 'Be strong; fear not! Behold, your God will come with vengeance, with the recompense of God. He will come and save you.'",
     "anxiety", ["strength", "salvation"], "mountains"),
    ("John 14:1", "Let not your hearts be troubled. Believe in God; believe also in me.",
     "anxiety", ["gospel", "jesus", "trust"], "candlelight"),
    ("Psalm 55:22", "Cast your burden on the Lord, and he will sustain you; he will never permit the righteous to be moved.",
     "anxiety", ["psalms", "surrender"], "mountains"),
    ("2 Timothy 1:7", "For God gave us a spirit not of fear but of power and love and self-control.",
     "anxiety", ["spirit", "power", "identity"], "sunrise"),

    # ═══════════ PSALMS (general) ═══════════
    ("Psalm 23:1-3", "The Lord is my shepherd; I shall not want. He makes me lie down in green pastures. He leads me beside still waters. He restores my soul. He leads me in paths of righteousness for his name's sake.",
     "psalms", ["shepherd", "rest", "guidance"], "fields"),
    ("Psalm 27:1", "The Lord is my light and my salvation; whom shall I fear? The Lord is the stronghold of my life; of whom shall I be afraid?",
     "psalms", ["courage", "protection"], "sunrise"),
    ("Psalm 91:1-2", "He who dwells in the shelter of the Most High will abide in the shadow of the Almighty. I will say to the Lord, 'My refuge and my fortress, my God, in whom I trust.'",
     "psalms", ["refuge", "protection", "trust"], "mountains"),
    ("Psalm 118:24", "This is the day that the Lord has made; let us rejoice and be glad in it.",
     "psalms", ["joy", "gratitude"], "sunrise"),
    ("Psalm 37:4", "Delight yourself in the Lord, and he will give you the desires of your heart.",
     "psalms", ["delight", "desire", "promise"], "fields"),
    ("Psalm 19:1", "The heavens declare the glory of God, and the sky above proclaims his handiwork.",
     "psalms", ["creation", "glory", "wonder"], "stars"),
    ("Psalm 139:14", "I praise you, for I am fearfully and wonderfully made. Wonderful are your works; my soul knows it very well.",
     "psalms", ["identity", "creation", "praise"], "sunrise"),
    ("Psalm 62:1-2", "For God alone my soul waits in silence; from him comes my salvation. He alone is my rock and my salvation, my fortress; I shall not be greatly shaken.",
     "psalms", ["waiting", "stability", "trust"], "mountains"),

    # ═══════════ PROVERBS ═══════════
    ("Proverbs 3:5-6", "Trust in the Lord with all your heart, and do not lean on your own understanding. In all your ways acknowledge him, and he will make straight your paths.",
     "proverbs", ["trust", "guidance", "faith"], "forests"),
    ("Proverbs 18:10", "The name of the Lord is a strong tower; the righteous man runs into it and is safe.",
     "proverbs", ["safety", "refuge"], "mountains"),
    ("Proverbs 15:1", "A soft answer turns away wrath, but a harsh word stirs up anger.",
     "proverbs", ["speech", "relationships", "wisdom"], "candlelight"),
    ("Proverbs 27:17", "Iron sharpens iron, and one man sharpens another.",
     "proverbs", ["community", "growth"], "mountains"),
    ("Proverbs 4:23", "Keep your heart with all vigilance, for from it flow the springs of life.",
     "proverbs", ["heart", "guard", "life"], "rivers"),
    ("Proverbs 16:3", "Commit your work to the Lord, and your plans will be established.",
     "proverbs", ["work", "commitment", "plans"], "fields"),
    ("Proverbs 17:17", "A friend loves at all times, and a brother is born for adversity.",
     "proverbs", ["friendship", "love", "loyalty"], "candlelight"),
    ("Proverbs 31:25", "Strength and dignity are her clothing, and she laughs at the time to come.",
     "proverbs", ["womanhood", "strength", "joy"], "fields"),

    # ═══════════ GOSPEL TEACHINGS ═══════════
    ("Matthew 5:14-16", "You are the light of the world. A city set on a hill cannot be hidden. Nor do people light a lamp and put it under a basket, but on a stand, and it gives light to all in the house. In the same way, let your light shine before others, so that they may see your good works and give glory to your Father who is in heaven.",
     "gospel", ["jesus", "identity", "witness"], "sunrise"),
    ("Matthew 6:33", "But seek first the kingdom of God and his righteousness, and all these things will be added to you.",
     "gospel", ["jesus", "priority", "kingdom"], "sunrise"),
    ("John 8:12", "Again Jesus spoke to them, saying, 'I am the light of the world. Whoever follows me will not walk in darkness, but will have the light of life.'",
     "gospel", ["jesus", "light", "life"], "sunrise"),
    ("Matthew 22:37-39", "And he said to him, 'You shall love the Lord your God with all your heart and with all your soul and with all your mind. This is the great and first commandment. And a second is like it: You shall love your neighbor as yourself.'",
     "gospel", ["jesus", "love", "commandments"], "candlelight"),
    ("John 16:33", "I have said these things to you, that in me you may have peace. In the world you will have tribulation. But take heart; I have overcome the world.",
     "gospel", ["jesus", "peace", "victory"], "mountains"),
    ("Matthew 7:7", "Ask, and it will be given to you; seek, and you will find; knock, and it will be opened to you.",
     "gospel", ["jesus", "prayer", "promise"], "candlelight"),
    ("John 14:6", "Jesus said to him, 'I am the way, and the truth, and the life. No one comes to the Father except through me.'",
     "gospel", ["jesus", "truth", "salvation"], "stained_glass"),
    ("Matthew 11:28-30", "Come to me, all who labor and are heavy laden, and I will give you rest. Take my yoke upon you, and learn from me, for I am gentle and lowly in heart, and you will find rest for your souls. For my yoke is easy, and my burden is light.",
     "gospel", ["jesus", "rest", "gentleness"], "fields"),

    # ═══════════ HARDSHIP ═══════════
    ("James 1:2-4", "Count it all joy, my brothers, when you meet trials of various kinds, for you know that the testing of your faith produces steadfastness. And let steadfastness have its full effect, that you may be perfect and complete, lacking in nothing.",
     "hardship", ["trials", "growth", "perseverance"], "mountains"),
    ("Romans 5:3-5", "Not only that, but we rejoice in our sufferings, knowing that suffering produces endurance, and endurance produces character, and character produces hope, and hope does not put us to shame, because God's love has been poured into our hearts through the Holy Spirit who has been given to us.",
     "hardship", ["suffering", "character", "love"], "sunrise"),
    ("1 Peter 4:12-13", "Beloved, do not be surprised at the fiery trial when it comes upon you to test you, as though something strange were happening to you. But rejoice insofar as you share Christ's sufferings, that you may also rejoice and be glad when his glory is revealed.",
     "hardship", ["trials", "christ", "joy"], "fire"),
    ("Isaiah 43:18-19", "Remember not the former things, nor consider the things of old. Behold, I am doing a new thing; now it springs forth, do you not perceive it? I will make a way in the wilderness and rivers in the desert.",
     "hardship", ["new", "hope", "transformation"], "desert"),
    ("Psalm 34:17-18", "When the righteous cry for help, the Lord hears and delivers them out of all their troubles. The Lord is near to the brokenhearted and saves the crushed in spirit.",
     "hardship", ["psalms", "help", "comfort"], "candlelight"),
    ("2 Corinthians 4:17", "For this light momentary affliction is preparing for us an eternal weight of glory beyond all comparison.",
     "hardship", ["perspective", "eternal", "glory"], "sunrise"),
    ("Romans 8:18", "For I consider that the sufferings of this present time are not worth comparing with the glory that is to be revealed to us.",
     "hardship", ["perspective", "glory", "hope"], "sunrise"),
    ("Psalm 30:5", "For his anger is but for a moment, and his favor is for a lifetime. Weeping may tarry for the night, but joy comes with the morning.",
     "hardship", ["psalms", "joy", "hope"], "sunrise"),
]


# ── Content provider ────────────────────────────────────────────────────────

class BibleContentProvider:
    """Provides Bible verse content for the shorts pipeline.

    Supports filtering by category, tag, and verse length constraints.
    Designed so additional categories / verses can be added without
    modifying any other module.
    """

    def __init__(self):
        self._verses: list[BibleVerse] = []
        self._by_category: dict[str, list[BibleVerse]] = {}
        self._load_verses()

    def _load_verses(self):
        """Parse the VERSES list into BibleVerse objects."""
        for ref, text, category, tags, bg in VERSES:
            # Parse "Book Chapter:Verse" reference
            # Handles "John 3:16", "Psalm 23:1-3", "Numbers 6:24-26", etc.
            parts = ref.rsplit(" ", 1)
            book = parts[0] if len(parts) > 0 else ref
            chapter_verse = parts[1] if len(parts) > 1 else "1:1"
            cv_parts = chapter_verse.split(":")
            chapter = int(cv_parts[0]) if cv_parts else 1
            # Verse may be a range like "24-26" or "1-3" — take the first number
            verse_str = cv_parts[1] if len(cv_parts) > 1 else "1"
            # Strip any non-digit suffix (e.g. "24-26" -> "24", "1a" -> "1")
            import re as _re
            verse_match = _re.match(r"(\d+)", verse_str)
            verse = int(verse_match.group(1)) if verse_match else 1

            bv = BibleVerse(
                reference=ref,
                book=book,
                chapter=chapter,
                verse=verse,
                text=text,
                category=category,
                tags=tags,
                theme_background=bg,
            )

            # Enforce length limits
            if cfg.MIN_VERSE_CHARS <= len(text) <= cfg.MAX_VERSE_CHARS:
                self._verses.append(bv)
                self._by_category.setdefault(category, []).append(bv)

    @property
    def categories(self) -> list[str]:
        """Return all available categories."""
        return sorted(self._by_category.keys())

    def get_verses_by_category(self, category: str) -> list[BibleVerse]:
        """Return all verses for a given category."""
        return self._by_category.get(category, [])

    def get_random_verse(self, category: Optional[str] = None) -> Optional[BibleVerse]:
        """Return a random verse, optionally from a specific category."""
        if category and category in self._by_category:
            pool = self._by_category[category]
        else:
            pool = self._verses
        return random.choice(pool) if pool else None

    def get_verses_by_tag(self, tag: str) -> list[BibleVerse]:
        """Return all verses matching a given tag."""
        return [v for v in self._verses if tag in v.tags]

    def get_random_by_tags(self, tags: list[str]) -> Optional[BibleVerse]:
        """Return a random verse matching any of the given tags."""
        pool = [v for v in self._verses if any(t in v.tags for t in tags)]
        return random.choice(pool) if pool else None

    def get_verse_by_reference(self, reference: str) -> Optional[BibleVerse]:
        """Look up a verse by its exact reference string."""
        ref_lower = reference.strip().lower()
        for v in self._verses:
            if v.reference.lower() == ref_lower:
                return v
        return None

    def get_daily_batch(self, count: int = 5, exclude_categories: Optional[list[str]] = None) -> list[BibleVerse]:
        """Return a diverse daily batch of verses, avoiding repeats within the batch."""
        exclude = set(exclude_categories or [])
        available_cats = [c for c in self.categories if c not in exclude]

        if not available_cats:
            available_cats = self.categories

        # Cycle through categories for diversity
        verses: list[BibleVerse] = []
        used_refs: set[str] = set()

        cat_idx = 0
        attempts = 0
        while len(verses) < count and attempts < count * 3:
            cat = available_cats[cat_idx % len(available_cats)]
            cat_idx += 1
            pool = [v for v in self._by_category.get(cat, []) if v.reference not in used_refs]
            if pool:
                v = random.choice(pool)
                verses.append(v)
                used_refs.add(v.reference)
            attempts += 1

        return verses


# Singleton instance
_provider: Optional[BibleContentProvider] = None


def get_provider() -> BibleContentProvider:
    """Return the singleton BibleContentProvider instance."""
    global _provider
    if _provider is None:
        _provider = BibleContentProvider()
    return _provider
