"""Regenerates the SYNTHETIC fixtures in this folder (ads, labels, placeholder images). Usage: python fixtures/make_fixtures.py fixtures"""
import csv, json, os, struct, sys, zlib

OUT = sys.argv[1]
PAGES = {
    "P": ("900000000000001", "Pinwheel Puzzle Co"),
    "B": ("900000000000002", "Brickfall Studios"),
    "I": ("900000000000003", "Ironhold Games"),
    "L": ("900000000000004", "Lumen Forge"),
}
# (key, start, stop, body, title, hook, cta, features)
ADS = [
 ("P","2026-05-03","2026-09-28","Only 2% of players pass level 7. Think you're one of them? Download free.","Pinwheel Puzzle - Free","fail_challenge","install","levels"),
 ("P","2026-05-10","2026-06-02","Watch every tile click perfectly into place. Pure calm, no timers. Play now.","Relax with Pinwheel","satisfying","play_now",""),
 ("P","2026-05-21",None,"Sort the colours, clear the board, breathe out. The most satisfying puzzle on your phone. Install today.","Pinwheel Puzzle","satisfying","install",""),
 ("P","2026-06-05","2026-06-30","Pull the right pin to save the cat! Most people pick the wrong one. Play now!","Can you save it?","fake_gameplay","play_now",""),
 ("P","2026-06-18","2026-08-10","1000+ handcrafted levels. Play offline, anywhere. Get it free.","Pinwheel Puzzle","other","install","levels,offline"),
 ("P","2026-07-02",None,"Grandma Rose lost her flower shop. Solve puzzles to rebuild it, one room at a time. Download now.","Help Rose rebuild","story","install",""),
 ("P","2026-07-15","2026-07-29","I bet you can't beat level 12 without a hint.","Pinwheel Puzzle","fail_challenge","none","levels"),
 ("P","2026-08-04","2026-10-30","Rose's daughter came home after ten years. Will they open the shop together? New chapter out now - play now.","Pinwheel: Rose's Story","story","play_now",""),
 ("P","2026-08-20","2026-09-05","So oddly satisfying. Swipe, match, repeat. No wifi needed. Install free.","Pinwheel Puzzle","satisfying","install","offline"),
 ("P","2026-09-12",None,"Decorate Rose's garden your way. Hundreds of styles to unlock. Download free.","Pinwheel Puzzle","other","install","customization"),
 ("P","2026-10-01",None,"Daily gifts every time you log in. Download free today!","Pinwheel Puzzle","other","install","rewards"),
 ("B","2026-05-05","2026-05-25","Draw one line to stop the water from reaching the house. 90% fail! Play now.","Brickfall","fake_gameplay","play_now",""),
 ("B","2026-05-14","2026-08-31","Everyone gets stuck on this one. Can you clear it in 3 moves? Install free.","Brickfall Blocks","fail_challenge","install",""),
 ("B","2026-06-01","2026-06-20","Crush the blocks and hear that perfect crunch. Satisfying every time. Get it now.","Brickfall Blocks","satisfying","install",""),
 ("B","2026-06-12",None,"Pick the right key to escape the room. Only geniuses get it first try. Play now.","Escape now","fake_gameplay","play_now",""),
 ("B","2026-07-01","2026-07-21","Stack, drop, clear. Thousands of levels and no wifi needed. Download today.","Brickfall Blocks","other","install","levels,offline"),
 ("B","2026-07-19","2026-10-15","Can you beat your friends' high score? Challenge them now - play free.","Brickfall Blocks","fail_challenge","play_now","pvp"),
 ("B","2026-08-08","2026-08-22","Only real puzzle masters make it past level 50.","Brickfall Blocks","fail_challenge","none","levels"),
 ("B","2026-09-02",None,"Tom's bakery is about to close. Clear blocks to pay the rent and save his dream. Install now.","Save Tom's Bakery","story","install",""),
 ("B","2026-09-24",None,"Pull the pin, free the gold, avoid the lava. Most players choose wrong! Download free.","Brickfall Rescue","fake_gameplay","install",""),
 ("B","2026-10-10",None,"Limited time: claim 500 free coins this weekend only!","Brickfall Blocks","other","limited_offer","rewards"),
 ("B","2026-10-22",None,"Schau zu, wie jeder Block perfekt einrastet. So befriedigend. Jetzt installieren.","Brickfall Blocks","satisfying","install",""),
 ("I","2026-05-02","2026-10-25","Build your fortress, train your army, conquer the realm. Join millions of lords. Download free.","Ironhold: Realms","other","install",""),
 ("I","2026-05-16","2026-06-15","Team up with your clan to take down the dragon. Real-time co-op battles. Play now.","Ironhold: Realms","other","play_now","coop"),
 ("I","2026-06-03","2026-07-01","Pre-register now for Season 3 and get an exclusive legendary hero.","Ironhold Season 3","other","pre_register","rewards"),
 ("I","2026-06-25",None,"Your castle keeps growing even when you're offline. Come back to a stronger army. Install today.","Ironhold: Realms","other","install","idle"),
 ("I","2026-07-10","2026-08-05","The king was betrayed by his own brother. Rise as the rightful heir and reclaim the throne. Download now.","The Lost Heir","story","install",""),
 ("I","2026-07-28",None,"Every choice changes the war. Ally with the north or burn their villages?","Ironhold: Realms","story","play_now","story_choices"),
 ("I","2026-08-14","2026-09-01","Crush rival kingdoms in live PvP. Climb the leaderboard. Get it free.","Ironhold Arena","other","install","pvp"),
 ("I","2026-09-03",None,"Only 1% of commanders survive wave 30. Prove you're not like the rest. Install now.","Ironhold: Survive","fail_challenge","install",""),
 ("I","2026-09-19",None,"Choose the right gate or the army is lost! Most commanders pick wrong. Play now.","Ironhold: Gates","fake_gameplay","play_now",""),
 ("I","2026-10-05",None,"Can you defend the wall for 60 seconds? Nobody on our team could.","Ironhold: Survive","fail_challenge","none",""),
 ("I","2026-10-18",None,"Baue deine Festung und kämpfe gegen echte Spieler. Jetzt kostenlos spielen!","Ironhold: Realms","other","play_now","pvp"),
 ("L","2026-05-08","2026-07-30","Customise your hero with 200+ skins and forge legendary gear. Download free.","Lumen Forge","other","install","customization"),
 ("L","2026-05-27","2026-06-18","Idle heroes that fight for you 24/7. Collect rewards when you return. Install now.","Lumen Forge Idle","other","install","idle,rewards"),
 ("L","2026-06-14","2026-10-12","Mira was the last mage of a burned city. Guide her journey and decide who lives. Download today.","Lumen Forge: Mira","story","install","story_choices"),
 ("L","2026-07-06","2026-07-18","Melt the gold, pour the mould, watch the sword glow. So satisfying. Play now.","Lumen Forge","satisfying","play_now",""),
 ("L","2026-07-24",None,"Your heroes level up while you sleep. Log in for daily free summons. Get it free.","Lumen Forge Idle","other","install","idle,rewards"),
 ("L","2026-08-11","2026-09-10","Fight alongside friends in 4-player raids. Install now.","Lumen Forge","other","install","coop"),
 ("L","2026-08-30",None,"Forge, hammer, polish. Hours of relaxing crafting. Download free.","Lumen Forge","satisfying","install",""),
 ("L","2026-09-15","2026-10-01","Ends Sunday: double rewards on every raid. Don't miss out.","Lumen Forge","other","limited_offer","coop,rewards"),
 ("L","2026-10-02",None,"Mira's mentor returns as a traitor. Your choices decide the ending. Play now.","Lumen Forge: Mira","story","play_now","story_choices"),
 ("L","2026-10-20",None,"Pull the lever to drop the boss into the lava! Only 5% get it right. Play now!","Lumen Forge","fake_gameplay","play_now",""),
 ("L","2026-10-27",None,"Erschaffe deinen Helden mit über 200 Skins. Jetzt herunterladen.","Lumen Forge","other","install","customization"),
 ("P","2026-09-20","2026-10-15","Pre-register for Pinwheel Gardens and get 1000 free coins at launch.","Pinwheel Gardens","other","pre_register","rewards"),
 ("B","2026-08-28","2026-09-20","Brickfall 2 is coming. Pre-register today and be first in line.","Brickfall 2","other","pre_register",""),
 ("L","2026-09-01","2026-09-30","Mira's journey continues soon. Pre-register now to hear how her story ends.","Lumen Forge: Mira","story","pre_register",""),
 ("I","2026-08-25","2026-09-02","48 hours only: 3x speed-ups for all commanders. Play now.","Ironhold: Realms","other","limited_offer","rewards"),
 ("P","2026-10-12",None,"Last chance! Free premium pass ends tonight. Download now.","Pinwheel Puzzle","other","limited_offer","rewards"),
]
FOLDER = [
 ("Tidepool Arcade","casual","2026-06-01","2026-07-15","Help the little fish escape the shark! Choose the right tunnel. Play now.","fake_gameplay","play_now",""),
 ("Tidepool Arcade","casual","2026-06-20",None,"Pop every bubble and feel the stress melt away. Download free.","satisfying","install",""),
 ("Tidepool Arcade","casual","2026-07-10","2026-08-01","Only 3% can finish this maze. Are you in?","fail_challenge","none",""),
 ("Tidepool Arcade","casual","2026-08-05",None,"Finn the fish lost his family in the storm. Help him find his way home. Install now.","story","install",""),
 ("Tidepool Arcade","casual","2026-08-25","2026-09-15","Play offline on the plane, the train, anywhere. Get it free.","other","install","offline"),
 ("Tidepool Arcade","casual","2026-09-10",None,"Decorate your own aquarium with 300 fish and corals. Download today.","other","install","customization"),
 ("Tidepool Arcade","casual","2026-10-01",None,"Weekend event: triple pearls until Monday! Play now.","other","limited_offer","rewards"),
 ("Tidepool Arcade","casual","2026-10-15",None,"Can you beat your best friend's score? Send a challenge.","fail_challenge","none","pvp"),
]

def png(path, rgb):
    w = h = 16
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

labels = []
data = []
for n, (k, start, stop, body, title, hook, cta, feats) in enumerate(ADS):
    pid, pname = PAGES[k]
    ad_id = str(800000000000100 + n)
    ad = {
        "id": ad_id, "page_id": pid, "page_name": pname,
        "ad_creation_time": start, "ad_delivery_start_time": start,
        "ad_creative_bodies": [body], "ad_creative_link_titles": [title],
        "ad_snapshot_url": f"https://www.facebook.com/ads/archive/render_ad/?id={ad_id}",
        "publisher_platforms": ["facebook", "instagram"],
        "languages": ["de"] if any(w in body for w in ("Schau", "Baue", "Erschaffe")) else ["en"],
    }
    if stop:
        ad["ad_delivery_stop_time"] = stop
    data.append(ad)
    labels.append((ad_id, hook, cta, feats))

# Messy-but-documented cases. Labelled ads above; these exercise the loader.
# 1) no ad_creative_bodies (title only)  2) two bodies  3) same copy as an earlier ad under a new id
pid, pname = PAGES["P"]
data.append({"id": "800000000000900", "page_id": pid, "page_name": pname,
             "ad_delivery_start_time": "2026-10-03T07:00:00+0000",
             "ad_creative_link_titles": ["Pinwheel Puzzle"], "publisher_platforms": ["facebook"]})
labels.append(("800000000000900", "other", "none", ""))
pid, pname = PAGES["L"]
data.append({"id": "800000000000901", "page_id": pid, "page_name": pname,
             "ad_delivery_start_time": "2026-10-08T12:30:00+0000",
             "ad_creative_bodies": ["The forge never sleeps.", "Melt, pour, polish - watch the blade glow. So satisfying. Install now."],
             "ad_creative_link_titles": ["Lumen Forge"], "publisher_platforms": ["instagram"]})
labels.append(("800000000000901", "satisfying", "install", ""))
dup = dict(next(a for a in data if a.get("ad_creative_bodies", [""])[0].startswith("Pick the right key")))
dup.update({"id": "800000000000902", "ad_delivery_start_time": "2026-10-20T09:00:00+0000"})
dup.pop("ad_delivery_stop_time", None)
data.append(dup)  # unlabelled on purpose: dedupes onto the earlier creative

note = ("SYNTHETIC fixture written by hand to match the documented ads_archive / ArchivedAd "
        "response shape. Advertisers, page ids and ad ids are fictional. Not real Meta data.")
half = len(data) // 2
os.makedirs(f"{OUT}/api", exist_ok=True)
json.dump({"_synthetic_note": note, "data": data[:half],
           "paging": {"cursors": {"before": "QVFIUjAw", "after": "QVFIUjIy"},
                      "next": "https://graph.facebook.com/v23.0/ads_archive?after=QVFIUjIy&limit=22"}},
          open(f"{OUT}/api/page_001.json", "w"), indent=1, ensure_ascii=False)
json.dump({"_synthetic_note": note, "data": data[half:],
           "paging": {"cursors": {"before": "QVFIUjIy", "after": "QVFIUjQ0"}}},
          open(f"{OUT}/api/page_002.json", "w"), indent=1, ensure_ascii=False)
json.dump({"Pinwheel Puzzle Co": "puzzle", "Brickfall Studios": "puzzle",
           "Ironhold Games": "strategy", "Lumen Forge": "strategy"},
          open(f"{OUT}/genres.json", "w"), indent=1)

os.makedirs(f"{OUT}/folder/media", exist_ok=True)
with open(f"{OUT}/folder/ads.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ad_id", "advertiser", "genre", "first_seen", "last_seen", "text", "media"])
    for n, (adv, genre, start, stop, text, hook, cta, feats) in enumerate(FOLDER):
        ad_id = f"tp-{n+1:03d}"
        media = ""
        if n < 2:
            media = f"media/{ad_id}.png"
            png(f"{OUT}/folder/{media}", (220, 80, 60) if n == 0 else (60, 160, 220))
        w.writerow([ad_id, adv, genre, start, stop or "", text, media])
        labels.append((ad_id, hook, cta, feats))

with open(f"{OUT}/labels.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ad_id", "hook", "cta", "features"])
    w.writerows(labels)
print(len(labels), "labelled ads")
