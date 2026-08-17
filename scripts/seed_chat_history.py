"""
Seed rich chat histories for simulator testing.
Run: docker compose exec api python /app/scripts/seed_chat_history.py
"""
from datetime import datetime, timedelta
from app.mongo import get_chat_collection, get_embedding
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# account_id, telegram_user_id, display_name
FANS = [
    (3, 100001, "דני כהן"),
    (3, 100002, "Yossi M"),
    (4, 100003, "אבי לוי"),
    (4, 100004, "Mike T"),
    (5, 100005, "Tom K"),
]

# שיחות עשירות עם פרטים אישיים
HISTORIES = {
    100001: [  # דני כהן — עברית, ביישן, עובד לילות
        ("assistant", "היי דני, שמחה שכתבת 😊"),
        ("user", "היי, ראיתי את הפרופיל שלך ורציתי לדבר"),
        ("assistant", "אני מחכה לשמוע עליך 😏"),
        ("user", "אני עובד משמרות לילה במפעל, אז בלילות אני תמיד ער"),
        ("user", "קצת קשה לי חברתית, אני ביישן בדרך כלל"),
        ("assistant", "זה נחמד שאתה כותב לי בלילה 🌙"),
        ("user", "כן לילה זה הזמן השקט שלי. יש לי כלב בשם בוצי שתמיד שומר עליי"),
        ("user", "אני גר בחיפה, עיר יפה אבל קצת שקטה"),
        ("assistant", "חיפה זה מקום נהדר! ספר לי עוד עליך"),
        ("user", "אני אוהב דיג בסוף השבוע, זה מרגיע אותי"),
        ("user", "קניתי לפני שבועיים מנוי כי חשבתי שיהיה כיף"),
        ("assistant", "שמחה שהחלטת 💕 תמיד כיף לדעת שמישהו חדש מצטרף"),
        ("user", "כן... אני קצת ביישן אז קשה לי לכתוב"),
        ("user", "אבל בוצי יושב לידי עכשיו ואני מרגיש בסדר"),
    ],
    100002: [  # Yossi — עברית, עובד הייטק, גרוש
        ("assistant", "היי יוסי, שמחה לראות אותך כאן"),
        ("user", "שלום, ראיתי אותך בטלגרם"),
        ("assistant", "ספר לי עליך 😊"),
        ("user", "אני מפתח תוכנה, עובד בסטארטאפ בתל אביב"),
        ("user", "ימים ארוכים בעבודה, לפעמים עד 10 בלילה"),
        ("assistant", "וואו, קשה. איך אתה מתפרק?"),
        ("user", "אני גרוש שנה, אז יש לי זמן פנוי בערבים"),
        ("user", "אוהב לרוץ בפארק הירקון בבוקר, כל יום"),
        ("user", "ויש לי בן בן 8 שאצלי כל סוף שבוע שני"),
        ("assistant", "בן 8 זה גיל כיפי! בטח שמחה להיות איתו"),
        ("user", "כן הוא אוהב לגלוש, לקחתי אותו לים בשבוע שעבר"),
        ("user", "אני גם אוהב להכין אוכל, מתמחה בסושי בבית"),
        ("user", "לפעמים אני מרגיש בודד בערבים כשהבן לא אצלי"),
        ("assistant", "מבינה אותך, הערבים יכולים להיות שקטים מדי"),
        ("user", "בדיוק. לכן כתבתי"),
    ],
    100003: [  # אבי לוי — עברית, ספורטאי, חובב מוזיקה
        ("assistant", "שלום אבי, תודה שכתבת"),
        ("user", "היי, ראיתי אותך בקבוצה"),
        ("user", "אני מאמן כושר, עובד בחדר כושר בראשון לציון"),
        ("assistant", "אוה, מרשים! כמה שנים אתה מאמן?"),
        ("user", "שלוש שנים. לפני זה שיחקתי כדורגל בחובבים"),
        ("user", "הברך שלי נפצעה אז עברתי לאימון אנשים"),
        ("assistant", "אוי, כואב לי רק לשמוע על הברך"),
        ("user", "כן זה היה קשה. אבל מצאתי את המקום שלי"),
        ("user", "אני גם מנגן גיטרה, כבר 10 שנים"),
        ("user", "אני חי לבד, דירה קטנה בראשון. רגוע"),
        ("assistant", "גיטרה ואימון כושר, שילוב מעניין"),
        ("user", "כן, הגיטרה זה הנשמה שלי. מוזיקה מרגיעה אחרי יום עבודה"),
        ("user", "אני מנגן כל ערב לפני שאני הולך לישון"),
        ("user", "הייתי רוצה יום אחד לעשות ג'אם עם עוד מוזיקאים"),
    ],
    100004: [  # Mike T — English, programmer, gamer
        ("assistant", "Hey Mike, welcome!"),
        ("user", "Hi, I found your profile through a friend"),
        ("assistant", "Tell me about yourself 😊"),
        ("user", "I'm a backend engineer, working remotely from Austin Texas"),
        ("user", "Been remote for 3 years now, love the freedom but gets lonely"),
        ("assistant", "Remote work can be isolating. What do you do to connect?"),
        ("user", "I game a lot — mainly strategy games like Civilization"),
        ("user", "Also have two cats, Luna and Pixel, they keep me company"),
        ("assistant", "Luna and Pixel sound adorable! What do they do while you work?"),
        ("user", "Luna sleeps on my keyboard constantly, messes up my code lol"),
        ("user", "I also brew my own coffee, obsessed with pour-over method"),
        ("user", "Used to live in NYC but moved to Austin 2 years ago for cheaper rent"),
        ("assistant", "Austin is such a cool city! Do you get out much?"),
        ("user", "Yeah I hike Barton Creek on weekends, clears my head"),
        ("user", "I'm pretty introverted so this kind of connection is easier for me"),
    ],
    100005: [  # Tom K — English, chef, divorced
        ("assistant", "Hey Tom, nice to meet you!"),
        ("user", "Hey! I saw your profile and had to say hi"),
        ("assistant", "I'm glad you did 😊 tell me about yourself"),
        ("user", "I'm a chef, run a small Italian restaurant in Chicago"),
        ("user", "Been doing this for 15 years, love it but it's exhausting"),
        ("assistant", "15 years! You must have incredible stories from the kitchen"),
        ("user", "Oh man, so many. Kitchen life is chaotic but I love it"),
        ("user", "I'm divorced, two years now. It's been an adjustment"),
        ("user", "My daughter is 12, she visits every other weekend"),
        ("assistant", "How does she feel about having a chef dad?"),
        ("user", "She loves it, I make her homemade pasta every time she visits"),
        ("user", "I also play poker on Thursday nights with the guys, tradition"),
        ("user", "Trying to get back into dating but it's hard with my schedule"),
        ("user", "Usually finish at the restaurant around midnight"),
        ("assistant", "That's a late night. You must be exhausted by the time you're free"),
        ("user", "Yeah, this kind of connection is easier for me at this point in life"),
    ],
}


def seed():
    col = get_chat_collection()
    now = datetime.utcnow()

    for account_id, telegram_user_id, name in FANS:
        history = HISTORIES.get(telegram_user_id, [])
        if not history:
            continue

        # מוחק היסטוריה ישנה
        deleted = col.delete_many({"account_id": account_id, "telegram_user_id": telegram_user_id})
        logger.info(f"Deleted {deleted.deleted_count} old messages for {name}")

        for i, (role, content) in enumerate(history):
            timestamp = now - timedelta(hours=len(history) - i)
            doc = {
                "account_id": account_id,
                "telegram_user_id": telegram_user_id,
                "role": role,
                "content": content,
                "timestamp": timestamp,
            }
            try:
                doc["embedding"] = get_embedding(content)
            except Exception as e:
                logger.warning(f"Embedding failed for message {i}: {e}")
            col.insert_one(doc)

        logger.info(f"✓ Seeded {len(history)} messages for {name} (account {account_id})")

    logger.info("Done!")


if __name__ == "__main__":
    seed()
