"""Who's who: a built-in Star Trek cast table (names, nicknames, gender) used before Gemma has read a word.

Each entry: canonical name -> (gender, [other names the books use]).
The canonical names match Glen's reference voice files where he has one (kirk, spock, mccoy, ...),
so a fresh Star Trek novel comes out already cast.
"""

TREK = {
    'Kirk': ('male', ['James Kirk', 'James T. Kirk', 'Jim Kirk', 'Jim', 'Captain Kirk', 'Admiral Kirk', 'Jimmy',
                      'James', 'J.T.']),
    'Spock': ('male', ['Mr. Spock', 'Mister Spock', 'Commander Spock', 'Captain Spock', 'Ambassador Spock']),
    'McCoy': ('male', ['Leonard McCoy', 'Dr. McCoy', 'Doctor McCoy', 'Bones', 'Leonard', 'Len']),
    'Scott': ('male', ['Scotty', 'Montgomery Scott', 'Mr. Scott', 'Mister Scott', 'Commander Scott', 'Montgomery']),
    'Sulu': ('male', ['Hikaru Sulu', 'Mr. Sulu', 'Mister Sulu', 'Lieutenant Sulu', 'Captain Sulu', 'Hikaru']),
    'Chekov': ('male', ['Pavel Chekov', 'Mr. Chekov', 'Mister Chekov', 'Ensign Chekov', 'Pavel']),
    'Uhura': ('female', ['Nyota Uhura', 'Lieutenant Uhura', 'Nyota', 'Commander Uhura']),
    'Chapel': ('female', ['Christine Chapel', 'Nurse Chapel', 'Christine', 'Dr. Chapel', 'Doctor Chapel']),
    'Rand': ('female', ['Janice Rand', 'Yeoman Rand', 'Janice']),
    'Kyle': ('male', ['Lieutenant Kyle', 'Mr. Kyle']),
    'Sarek': ('male', ['Ambassador Sarek']),
    'Amanda': ('female', ['Amanda Grayson', 'Lady Amanda']),
    'Saavik': ('female', ['Lieutenant Saavik']),
    'Carol Marcus': ('female', ['Dr. Marcus', 'Carol', 'Doctor Marcus']),
    'David Marcus': ('male', ['David']),
    'Khan': ('male', ['Khan Noonien Singh', 'Khan Noonian Singh']),
    'Pike': ('male', ['Christopher Pike', 'Captain Pike', 'Chris Pike']),
    'Number One': ('female', ['Una']),
    'Kor': ('male', ['Commander Kor']),
    'Kang': ('male', ['Commander Kang']),
    'Koloth': ('male', ['Captain Koloth']),
    'Harry Mudd': ('male', ['Mudd', 'Harcourt Fenton Mudd']),
    'Leila Kalomi': ('female', ['Leila']),
    'Edith Keeler': ('female', ['Edith', 'Miss Keeler']),
    'Gary Mitchell': ('male', ['Mitchell']),
    'Finnegan': ('male', []),
    'Komack': ('male', ['Admiral Komack']),
    'Nogura': ('male', ['Admiral Nogura']),
    'Cartwright': ('male', ['Admiral Cartwright']),
    'Morrow': ('male', ['Admiral Morrow']),
    'Valeris': ('female', ['Lieutenant Valeris']),
    'Gorkon': ('male', ['Chancellor Gorkon']),
    'Azetbur': ('female', []),
    'Kruge': ('male', ['Commander Kruge']),
    'Riley': ('male', ['Kevin Riley', 'Lieutenant Riley']),
    "M'Benga": ('male', ['Dr. M\'Benga', 'Doctor M\'Benga']),
    'DeSalle': ('male', ['Lieutenant DeSalle']),
    'Leslie': ('male', ['Mr. Leslie']),
    'Giotto': ('male', ['Lieutenant Giotto', 'Lieutenant Commander Giotto']),
    # TNG and after, for when Glen strays
    'Picard': ('male', ['Jean-Luc Picard', 'Jean-Luc', 'Captain Picard']),
    'Riker': ('male', ['William Riker', 'Will Riker', 'Commander Riker', 'Number One']),
    'Data': ('male', ['Commander Data', 'Mr. Data']),
    'La Forge': ('male', ['Geordi', 'Geordi La Forge']),
    'Worf': ('male', ['Lieutenant Worf', 'Mr. Worf']),
    'Troi': ('female', ['Deanna', 'Deanna Troi', 'Counselor Troi']),
    'Crusher': ('female', ['Beverly', 'Beverly Crusher', 'Dr. Crusher', 'Doctor Crusher']),
    'Guinan': ('female', []),
    'Q': ('male', []),
}

# Book words that mean "the narrator", never a character
NOT_NAMES = {
    'The', 'A', 'An', 'He', 'She', 'It', 'They', 'We', 'You', 'I', 'His', 'Her', 'Their', 'Its', 'This', 'That',
    'There', 'Then', 'When', 'What', 'Where', 'Why', 'How', 'Who', 'But', 'And', 'Or', 'If', 'As', 'At', 'In', 'On',
    'Of', 'To', 'For', 'With', 'From', 'By', 'Yes', 'No', 'Not', 'Now', 'Well', 'Oh', 'Ah', 'Sir', 'Ma\'am',
    'Captain', 'Commander', 'Lieutenant', 'Doctor', 'Ensign', 'Admiral', 'Mister', 'Mr', 'Mrs', 'Ms', 'Dr',
    'Enterprise', 'Starfleet', 'Federation', 'Vulcan', 'Klingon', 'Klingons', 'Romulan', 'Romulans', 'Earth',
    'Chapter', 'Part', 'Book', 'Stardate', 'Captain’s', 'Log', 'God', 'Lord', 'Computer', 'Bridge',
    'Engineering', 'Sickbay', 'Transporter', 'Space', 'Warp', 'Impulse', 'Phaser', 'Phasers', 'Everyone', 'Someone',
    'Nobody', 'Nothing', 'All', 'One', 'Two', 'Three', 'Still', 'Just', 'Even', 'Only', 'Perhaps', 'Maybe', 'After',
    'Before', 'Again', 'Here', 'So', 'Then', 'Once', 'Some', 'Every', 'Each', 'Both', 'These', 'Those', 'Which',
    'While', 'Until', 'Because', 'Though', 'Although', 'Yet', 'Instead', 'Behind', 'Above', 'Below', 'Inside',
    'Outside', 'Without', 'Within', 'Against', 'Across', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
    'Saturday', 'Sunday', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
    'October', 'November', 'December', 'Christmas', 'English', 'Standard',
}

TITLES = ('Captain', 'Commander', 'Lieutenant', 'Doctor', 'Dr.', 'Ensign', 'Admiral', 'Mr.', 'Mister', 'Mrs.',
          'Ms.', 'Miss', 'Nurse', 'Yeoman', 'Chief', 'Ambassador', 'Professor', 'General', 'Colonel', 'Major',
          'Sergeant', 'Chancellor', 'Governor', 'Senator', 'Councillor', 'Councilor', 'Lady', 'Lord', 'Sir',
          'Subcommander', 'Centurion', 'Praetor', 'Proconsul', 'Commodore', 'Counselor')

FEMALE_TITLES = ('Mrs.', 'Ms.', 'Miss', 'Lady', 'Nurse', 'Yeoman')


def alias_table(characters):
    """{lowercase alias -> canonical name} for this book's characters."""
    out = {}
    for c in characters:
        names = [c['name']] + list(c.get('aliases') or [])
        for n in names:
            if n:
                out.setdefault(n.lower(), c['name'])
    return out


def trek_entry(name):
    if name in TREK:
        return name, TREK[name]
    low = name.lower()
    for k, (g, aliases) in TREK.items():
        if low == k.lower() or low in (a.lower() for a in aliases):
            return k, (g, aliases)
    return None, None
