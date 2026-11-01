"""Random script generator: builds a ready-to-render "hidden origins" countdown script of any length (8 minutes by
default) from a bank of hand-written, fact-checked stories, with chapters, sets, gestures, faces, moves, highlights,
footage and fact-card tags. Every press gives a different selection, order, hook, transitions and tags.

About 150 spoken words make one minute.
"""
import random
import re

WPM = 150

SEGMENTS = [
    dict(id='tree', title='The Christmas tree', set='christmas', clip='christmas tree lights', text="""
People were bringing evergreens indoors in winter long before Christmas existed. [explain]
The Romans decked their homes with greenery for the festival of *Saturnalia*.
But the decorated Christmas tree is usually traced to *Germany* in the 1500s. [point]
A popular legend says Martin Luther added candles after seeing stars through the branches. [shrug] Nice story, but there's no proof.
The real turning point came in 1848. [idea] A London newspaper printed a drawing of Queen Victoria and Prince Albert around a decorated tree.
Overnight, every fashionable family wanted one. [amazed]
And electric lights? In 1882, Edison's partner Edward Johnson wired up 80 red, white and blue bulbs. [note: The first electric tree lights: 1882]"""),
    dict(id='santa', title='Why Santa wears red', set='christmas', clip='santa claus', text="""
You've probably heard that Coca-Cola made Santa red. [point] It's one of the biggest Christmas myths. [shake]
Santa grew out of *Saint Nicholas*, a bishop who lived in what is now Turkey in the 300s.
In the 1800s, cartoonist Thomas Nast drew Santa for Harper's Weekly, and his Santa often wore red. [explain]
Magazine covers and postcards showed a red Santa years before any soft drink advert. [note: Santa was red long before Coca-Cola]
What Coca-Cola did, from 1931, was hire artist Haddon Sundblom to paint a warm, jolly Santa. [present]
Those adverts ran for decades and fixed that image in everyone's mind. [nod]
So Coca-Cola didn't invent the red suit. It just made it *famous*. [wink]"""),
    dict(id='halloween', title='Halloween began in Ireland', set='halloween', clip='halloween pumpkin night', text="""
Halloween started more than 2,000 years ago with a Celtic festival called *Samhain*. [explain]
It marked the end of the harvest, when people believed the wall between the living and the dead grew thin. [shocked]
In Ireland and Scotland, people carved scary faces into *turnips* to keep wandering spirits away. [idea]
In the 700s, the church placed All Saints' Day on the first of November, so the night before became All Hallows' Eve.
Then, in the 1800s, millions of Irish people emigrated to America. [present]
They brought their customs with them, and discovered that *pumpkins* were bigger and much easier to carve. [laugh]
That's how a turnip lantern from Ireland became the jack-o'-lantern on every American porch. [thumbs]"""),
    dict(id='valentine', title="The real Valentine's Day", set='history', clip='love letters roses', text="""
Valentine's Day is named after a Roman saint, but historians aren't even sure which one. [shrug]
There were several martyrs called *Valentine* in the third century, and we know very little about any of them. [confused]
The link to romance appears much later, in a poem by Geoffrey Chaucer in the 1380s. [idea]
He wrote that birds chose their mates on Saint Valentine's day. [love]
By the 1700s, English couples were swapping handwritten love notes. [explain]
Printed cards took off in the 1800s, and in America, Esther Howland sold beautifully decorated ones by the thousand. [present]
So the most romantic day of the year began with a bird poem. [laugh]"""),
    dict(id='bunny', title='Why a bunny brings Easter eggs', set='nature', clip='rabbit meadow spring', text="""
Rabbits don't lay eggs. [confused] So why does a bunny deliver them? [think]
Hares were old symbols of spring and new life, because they have so many babies. [explain]
In Germany, children were told about the *Osterhase*, the Easter hare. [point]
It judged whether kids had been good, and left coloured eggs for the ones who had. [happy]
German settlers brought the Osterhase to Pennsylvania in the 1700s. [present]
Children built little nests in their caps and bonnets for the hare to fill. [love]
Chocolate eggs and bunnies arrived in Europe in the 1800s, and the sweetest tradition of all was born. [celebrate]"""),
    dict(id='april', title='April Fools mystery', set='mystery', clip='magnifying glass mystery', text="""
Here's the funny part: nobody really knows how April Fools' Day began. [shrug] [laugh]
One popular theory blames France switching calendars in 1582. [explain]
People who still celebrated New Year in spring were mocked as fools. But historians have found no solid proof. [shake]
A Flemish poem from 1561 already describes a servant sent on silly errands on the first of April. [idea]
In 1698, Londoners were tricked into visiting the Tower to watch the lions being washed. [laugh]
And in 1957, the BBC showed farmers harvesting spaghetti from trees. [amazed]
Hundreds of viewers phoned in asking how to grow their own. [facepalm]"""),
    dict(id='candles', title='Birthday cake candles', set='studio', clip='birthday cake candles', text="""
Why do we blow out candles on a cake? [think]
Some historians think it goes back to ancient Greeks offering round cakes with candles to the moon goddess Artemis. [explain]
The custom we know clearly appears in 18th-century *Germany*, at a children's party called Kinderfest. [point]
Children got a cake with one candle for each year, plus one more for the year to come. [happy]
And the song? Its tune comes from Good Morning to All, written by two sisters in 1893. [present]
For decades a company collected fees whenever it was used in films. [mad]
Only in 2016 did Happy Birthday become free for everyone to sing. [celebrate]"""),
    dict(id='groundhog', title='Groundhog Day', set='nature', clip='groundhog', text="""
Every February, a groundhog predicts the weather. [laugh] How did that happen? [think]
In Europe, the Christian festival of Candlemas fell on the second of February.
An old saying claimed that a sunny Candlemas meant six more weeks of winter. [explain]
In Germany, people watched badgers and hedgehogs for a sign. [point]
German settlers in Pennsylvania found no badgers, so they picked the *groundhog* instead. [shrug]
The first official Groundhog Day in Punxsutawney was held in 1887. [present]
His accuracy? Studies put it at roughly 40 percent. [facepalm] You'd do better flipping a coin. [wink]"""),
    dict(id='resolutions', title="New Year's resolutions", set='history', clip='fireworks new year', text="""
Making New Year's resolutions is around 4,000 years old. [amazed]
The ancient Babylonians held a huge festival called *Akitu* to start their year. [explain]
They promised their gods to pay their debts and return anything they had borrowed. [count]
Keep your promises, and the gods would favour you. Break them, and you were in trouble. [mad]
The Romans named January after *Janus*, a god with two faces, one looking back and one looking forward. [point]
So the idea of looking back on the old year and planning the new one is ancient. [nod]
Sadly, keeping resolutions is just as hard as it was 4,000 years ago. [tired]"""),
    dict(id='rings', title='Why rings go on that finger', set='history', clip='wedding rings', text="""
Why does a wedding ring go on the fourth finger? [think]
Ancient Egyptians saw the circle as a symbol of eternity, with no beginning and no end. [explain]
The Romans believed a special vein ran from that finger straight to the heart. They called it the *vena amoris*, the vein of love. [love]
Modern anatomy says there's no such vein. [shake] But the romantic idea stuck. [shrug]
In 1477, Archduke Maximilian of Austria gave Mary of Burgundy one of the first recorded diamond engagement rings. [present]
And in 1947, a diamond company launched the slogan "A diamond is forever." [amazed]
It's still one of the most successful adverts ever written. [nod]"""),
    dict(id='handshake', title='The handshake', set='history', clip='handshake', text="""
We shake hands without thinking, but the gesture is ancient. [explain]
A carving from the 800s BC shows an Assyrian king shaking hands with a Babylonian ruler. [point]
A popular theory says it proved you weren't holding a weapon. [stop] Nice idea, though nobody can prove it. [shrug]
What we do know is who spread it: the *Quakers* in the 1600s. [idea]
They thought bowing and hat-tipping made some people seem better than others. [focused]
A handshake treated everyone as equals. [nod]
So the next time you shake someone's hand, you're doing something that was once a small rebellion. [cool]"""),
    dict(id='jeans', title='Jeans were made for miners', set='studio', clip='denim jeans', text="""
Blue jeans started as work clothes for miners in the American West. [explain]
In 1873, a merchant named *Levi Strauss* and a tailor named Jacob Davis patented trousers with copper rivets. [point]
The rivets stopped pockets ripping when miners stuffed them with tools and rocks. [idea]
The words come from Europe: jean from the Italian city of Genoa, and denim from the French town of Nîmes. [present]
For decades, jeans were just tough workwear. [shrug]
Then, in the 1950s, film stars like James Dean wore them on screen. [cool]
Suddenly, workwear became the uniform of rebellion. [amazed]"""),
    dict(id='fork', title='The scandal of the fork', set='history', clip='silver fork dining', text="""
Believe it or not, the fork was once a scandal. [surprised]
In the 1000s, a Byzantine princess married into a noble family in *Venice*. [explain]
At dinner, she ate with a little golden fork instead of her fingers. [present]
Church leaders were horrified. One called it vanity. [mad]
Forks slowly caught on in Italy, but when an English traveller brought one home in 1608, people laughed at him. [laugh]
It took until the 1700s for forks to be normal on English tables. [nod]
So the most ordinary thing in your kitchen drawer was once a shocking luxury. [amazed]"""),
    dict(id='ok', title='Where OK came from', set='studio', clip='old newspaper printing', text="""
OK might be the most used word on the planet. And it started as a joke. [laugh]
In 1839, Boston newspapers had a craze for silly abbreviations of misspelled phrases. [explain]
*OK* stood for "oll korrect", a joke spelling of all correct. [wink]
Most of those jokes died out, but OK got lucky. [shrug]
In 1840, President Martin Van Buren ran for re-election. His nickname was Old Kinderhook, after his hometown. [present]
His supporters formed OK Clubs, and the word spread across the country. [celebrate]
Telegraph operators loved it because it was short. [nod] Today, it's understood almost everywhere. [amazed]"""),
    dict(id='toothfairy', title='The tooth fairy', set='studio', clip='child smiling tooth', text="""
The tooth fairy is surprisingly young. [surprised]
People have had rituals for baby teeth for centuries. Some burned them, some buried them, some fed them to animals. [explain]
In Spain, a little mouse called *Ratoncito Pérez* collects teeth. [happy]
His story was written in 1894 for a young king who had just lost a tooth. [present]
The American tooth fairy appears in newspapers in the early 1900s. [point]
Parents loved it, because it turned a scary moment into a little bit of magic. [love]
And the going rate has climbed a lot since then. [laugh]"""),
    dict(id='friday13', title='Why Friday the 13th is unlucky', set='mystery', clip='black cat night', text="""
Friday the 13th scares millions of people. [shocked] But the fear is younger than you think.
Thirteen was seen as unlucky for a long time, partly because of the 13 guests at the Last Supper. [explain]
Fridays had a bad reputation in Chaucer's time too. [shrug]
But the two only joined together in the 1800s. [idea]
In 1907, a bestselling novel called Friday, the Thirteenth made the idea famous. [present]
Some people link it to the arrest of the Knights Templar on Friday the 13th of October 1307, but that link was made centuries later. [suspicious]
The fear even has a name: paraskevidekatriaphobia. [dizzy]"""),
    dict(id='sandwich', title='The Earl of Sandwich', set='history', clip='sandwich', text="""
The sandwich is named after a real person: *John Montagu*, the fourth Earl of Sandwich. [point]
The famous story says he didn't want to leave the card table, so he asked for meat between two slices of bread. [laugh]
That way he could eat with one hand and keep playing. [present]
His biographer thinks he was more likely working late at his desk. [shrug]
Either way, his friends started ordering "the same as Sandwich", and the name stuck in the 1700s. [nod]
Of course, people had been putting food on bread for thousands of years before him. [explain]
He just got the credit. [wink]"""),
    dict(id='ketchup', title='Ketchup was a fish sauce', set='ocean', clip='fishing boats harbour', text="""
Ketchup started out as a sauce made from *fish*. [surprised]
In southern China, a fermented fish sauce was called something like *kê-tsiap*. [explain]
British sailors tasted it in Asia in the 1600s and brought the idea home. [present]
English cooks tried making it with mushrooms, walnuts and even oysters. [laugh]
The first known tomato ketchup recipe was published in America in 1812. [idea]
In 1876, Henry Heinz began selling his own bottled tomato ketchup. [point]
So the sauce on your fries is really the great-grandchild of a fish sauce. [amazed]"""),
    dict(id='champagne', title='Who really invented champagne', set='history', clip='champagne bubbles', text="""
Legend says a monk named *Dom Pérignon* invented champagne and shouted, "I am drinking the stars!" [celebrate]
That quote actually comes from an advert written about 200 years later. [facepalm]
In fact, Dom Pérignon spent years trying to get rid of the bubbles. [shocked]
They made bottles explode in the cellars. [jump]
In 1662, an English scientist named Christopher Merret described adding sugar to wine to make it sparkle. [idea]
English glassmakers were making bottles strong enough to survive the pressure. [explain]
So the English helped give champagne its fizz before the famous monk's legend was born. [wink]"""),
    dict(id='blessyou', title='Why we say bless you', set='mystery', clip='person sneezing', text="""
Why do we say bless you when someone sneezes? [think]
One story points to the year 590, when a terrible plague hit Rome. [shocked]
Pope Gregory the First is said to have asked people to pray for anyone who sneezed. [explain]
But the habit is older still. Ancient Greeks and Romans also wished sneezers good health. [present]
Some old folk beliefs said a sneeze could shake your soul loose. [dizzy]
Others thought it pushed evil spirits out. [suspicious]
Whatever the reason, it's a habit that has survived for well over a thousand years. [nod]"""),
    dict(id='heels', title='High heels were made for men', set='history', clip='horse riding', text="""
High heels were first made for *men*. [surprised]
Persian horsemen wore heels to keep their feet steady in the stirrups while shooting arrows. [explain]
When Persian diplomats visited Europe around 1600, European nobles copied the look. [present]
Heels made men look taller and richer, because you couldn't work in a field wearing them. [cool]
King Louis the Fourteenth of France loved red heels and allowed only his court to wear them. [point]
Women adopted heels too, and by the 1700s, men had mostly given them up. [shrug]
Fashion has a funny way of swapping sides. [laugh]"""),
    dict(id='pinkblue', title='Pink used to be for boys', set='studio', clip='baby clothes', text="""
For most of history, babies of all genders wore white. It was easy to bleach. [explain]
In 1918, a trade magazine advised pink for boys and blue for girls. [shocked]
Pink was seen as a stronger colour, and blue as delicate and dainty. [present]
Different shops gave completely different advice for years. [confused]
It wasn't until around the 1940s that the rule settled the other way round. [point]
Shops and advertisers made it stick. [nod]
So the "rule" we think is ancient is less than a hundred years old. [amazed]"""),
    dict(id='barber', title='The barber pole', set='history', clip='barber shop', text="""
The barber pole has a bloody history. [shocked]
In medieval Europe, barbers didn't just cut hair. They pulled teeth and performed bloodletting. [explain]
Patients gripped a pole to make their veins stand out. [count]
The red and white stripes stand for blood and bandages. [point]
Bandages were washed and hung outside to dry, twisting around the pole in the wind. [present]
In England, barbers and surgeons were part of the same company until 1745. [idea]
So that cheerful spinning pole is a reminder of a much scarier haircut. [laugh]"""),
    dict(id='fortune', title='Fortune cookies are not Chinese', set='tech', clip='fortune cookie', text="""
Fortune cookies are almost unknown in China. [surprised]
Historians trace them to *Japan*, where bakers in Kyoto made crackers with little fortunes tucked inside. [explain]
Japanese immigrants brought them to California in the early 1900s. [present]
San Francisco and Los Angeles both claim to be their true home. [shrug]
During the Second World War, Japanese American families were sent to camps, and Chinese American bakeries took over making them. [sad]
That's how they became a fixture of Chinese restaurants in America. [nod]
In 1983, a mock court in San Francisco even ruled on who invented them. [laugh]"""),
]

TITLES = ['{n} Hidden Origins You Never Knew', 'The Secret History of {n} Everyday Things',
          '{n} Traditions With Surprising Origins', '{n} Things You Believe That Started By Accident',
          'Where Did This Come From? {n} Hidden Origins']
HOOKS = [
    "Almost everything you do on a normal day has a secret history. [point] [excited]\nAnd some of those stories are stranger than fiction. [amazed]",
    "What if I told you that half the traditions you love started by accident? [think]\nToday we're uncovering {n} of them. [point] [excited]",
    "You do these things every year without thinking. [shrug]\nBut where did they actually come from? [think] Let's find out. [nod]",
]
INTROS = [
    "I'm counting down {n} hidden origins, and the last one might surprise you most. [count]\nGet comfortable. This is going to be fun. [happy]",
    "We're going back thousands of years, across {n} stories. [explain]\nSome are funny, some are dark, and one is a total myth. [wink]",
    "Here are {n} everyday things with surprising origins. [present]\nStay until the end for my favourite one. [happy]",
]
TRANSITIONS = ['Next up.', 'Now this one is wild.', "Here's a strange one.", 'Moving on.', 'Next, a story you probably got wrong.',
               'This one surprised me.', 'Ready for another?', 'Now for something completely different.']
OUTROS = [
    "And that's our countdown. [nod]\nWhich one surprised you the most? Tell me in the comments. [think]\nSubscribe for more hidden origins, and I'll see you next time. [wave] [happy]",
    "So the next time you do any of these things, you'll know the real story. [cool]\nIf you learned something new, hit subscribe. [thumbs]\nSee you in the next one! [wave]",
]
EXTRA_MOVES = ['[nod]', '[tilt]', '[lean]', '[bounce]', '[look around]']
NUMBER_WORDS = {1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six', 7: 'Seven', 8: 'Eight', 9: 'Nine', 10: 'Ten',
                11: 'Eleven', 12: 'Twelve'}


def words(text):
    text = re.sub(r'\[[^\]]*\]', ' ', text)
    return len([w for w in text.split() if not w.startswith('#')])


def generate(minutes=8, seed=None, footage=True):
    """Returns (script, info). minutes: target length; about 150 words a minute."""
    rnd = random.Random(seed)
    target = max(1, float(minutes)) * WPM
    pool = SEGMENTS[:]
    rnd.shuffle(pool)
    chosen, total = [], 110
    for seg in pool:
        if chosen and total >= target - 50:
            break
        chosen.append(seg)
        total += words(seg['text']) + 6
    n = len(chosen)
    title = rnd.choice(TITLES).format(n=NUMBER_WORDS.get(n, str(n)))
    if n == 1:
        title = 'The Surprising Story of ' + chosen[0]['title'].replace('The ', 'the ', 1)
    out = [f'# {title}', rnd.choice(HOOKS).format(n=n), rnd.choice(INTROS).format(n=n), '']
    for i, seg in enumerate(chosen):
        num = n - i
        out.append(f"# Number {num}: {seg['title']}")
        lines = [l.strip() for l in seg['text'].strip().split('\n') if l.strip()]
        lead = rnd.choice(TRANSITIONS) if i else 'Let’s start.'
        lines[0] = f"[set: {seg['set']}] {lead} {lines[0]}"
        if footage:
            k = rnd.randrange(1, max(2, len(lines) - 1))
            tag = 'broll' if rnd.random() < 0.35 else 'clip'
            lines[k] = lines[k] + f" [{tag}: {seg['clip']}]"
        if rnd.random() < 0.6:
            k = rnd.randrange(len(lines))
            if not any(m in lines[k] for m in EXTRA_MOVES):
                lines[k] += ' ' + rnd.choice(EXTRA_MOVES)
        out.extend(lines)
        out.append('')
    out.append('# Thanks for watching')
    out.append(rnd.choice(OUTROS))
    script = '\n'.join(out).strip() + '\n'
    wc = words(script)
    return script, dict(title=title, stories=n, words=wc, minutes=round(wc / WPM, 1))


if __name__ == '__main__':
    s, info = generate()
    print(s)
    print(info)
