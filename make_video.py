"""Command line version:  python make_video.py script.txt --out out_folder [--audio my_voice.mp3] [--landscape]"""
import argparse

from pipeline import make_video


def main():
    ap = argparse.ArgumentParser(description='Make a talking-character video from a script.')
    ap.add_argument('script', help='path to a .txt or .md script')
    ap.add_argument('--out', default='output', help='output folder')
    ap.add_argument('--audio', help='use this recording instead of generating a voice')
    ap.add_argument('--voice', default='en-US-AndrewNeural', help="neural voice name, or a Windows voice with --windows")
    ap.add_argument('--windows', action='store_true', help='use the offline Windows voice')
    ap.add_argument('--speed', type=int, default=0, help='speech speed in percent, -30 to +30')
    ap.add_argument('--landscape', action='store_true', help='16:9 instead of 9:16')
    ap.add_argument('--draft', action='store_true', help='half-size fast render')
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--seconds', type=float, help='only render the first N seconds')
    ap.add_argument('--captions', default='bold', choices=['bold', 'box', 'minimal', 'off'], help='caption style')
    ap.add_argument('--set', default='auto', help='auto, or one of: studio christmas halloween history space tech nature ocean mystery')
    ap.add_argument('--static-camera', action='store_true', help='no camera moves')
    ap.add_argument('--music', help='background music file (mp3/wav/m4a)')
    ap.add_argument('--music-volume', type=float, default=0.22)
    ap.add_argument('--images', action='store_true', help='show royalty-free pictures on the set screen')
    ap.add_argument('--sources', default='wikimedia,nasa,cleveland',
                    help='comma list: openverse,wikimedia,nasa,cleveland,pexels,pixabay,unsplash')
    ap.add_argument('--character', default='classic', choices=['classic', 'theme', 'random', 'custom'],
                    help='classic = your character sheet, theme = dressed for each set, random = new look per scene, custom = the options below')
    ap.add_argument('--outfit', default='hoodie', help='hoodie zip varsity puffer sweater flannel labcoat suit trench raincoat astro')
    ap.add_argument('--hat', default='cap', help='cap cap_back beanie beanie_pom bucket santa witch top wizard cowboy fedora captain helmet hood crown none')
    ap.add_argument('--color', default='charcoal', help='outfit colour, e.g. charcoal midnight crimson forest royal plum mustard')
    ap.add_argument('--accent', default='blue', help='glow colour: blue cyan mint lime magenta violet orange gold red white')
    ap.add_argument('--my-character', help='id of a character you uploaded in the app (replaces the built-in one)')
    ap.add_argument('--look-seed', type=int, default=0, help='change this number for different random looks')
    ap.add_argument('--footage', choices=['screen', 'inside', 'bubble', 'mix'],
                    help='use video footage: on the set screen, full screen with the character in the shot, full screen with a bubble, or a mix')
    ap.add_argument('--footage-sources', default='mine,pexels,pixabay,wikimedia,nasa')
    ap.add_argument('--strict-licenses', action='store_true', help='only pictures that need no credit')
    a = ap.parse_args()
    images = dict(mode='auto', sources=a.sources.split(','), license='strict' if a.strict_licenses else 'standard') if a.images else None
    look = dict(set_mode=a.set, camera='static' if a.static_camera else 'dynamic', caption_style=a.captions,
                character=dict(mode=a.character, seed=a.look_seed,
                               custom=dict(outfit=a.outfit, hat=a.hat, color=a.color, accent=a.accent)))
    if a.my_character:
        look['character'] = dict(mode='image', image_id=a.my_character)
    music = dict(path=a.music, volume=a.music_volume) if a.music else None
    clips = dict(display=a.footage, sources=a.footage_sources.split(',')) if a.footage else None
    text = open(a.script, encoding='utf-8-sig').read()
    mode = 'file' if a.audio else ('windows' if a.windows else 'edge')
    res = make_video(text, a.out, mode=mode, voice=a.voice if mode != 'windows' else (a.voice if a.voice != 'en-US-AndrewNeural' else ''),
                     speed=a.speed, audio_path=a.audio, fmt='landscape' if a.landscape else 'vertical',
                     quality='draft' if a.draft else 'final', fps=a.fps, captions=a.captions != 'off', seconds=a.seconds,
                     images=images, look=look, music=music, video_clips=clips,
                     progress=lambda m, f: print(f'{m} {int((f or 0) * 100)}%', flush=True))
    print('Saved', res['video'])
    print('Sets:', ', '.join(f"{s['theme']} ({s['title']})" for s in res['sets']))
    if res.get('credits'):
        print('Credits file:', res['credits'])
    for w in res.get('warnings', []):
        print('Warning:', w)


if __name__ == '__main__':
    main()
