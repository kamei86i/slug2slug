# -*- coding: utf-8 -*-

import os
import io
import string
import re
import itertools
from collections import OrderedDict
from nltk.tokenize import word_tokenize, sent_tokenize

import config
from slot_aligner.alignment.utils import find_first_in_list
from slot_aligner.alignment.boolean_slot import align_boolean_slot
from slot_aligner.alignment.list_slot import align_list_slot, align_list_with_conjunctions_slot
from slot_aligner.alignment.numeric_slot import align_numeric_slot_with_unit, align_year_slot
from slot_aligner.alignment.scalar_slot import align_scalar_slot
from slot_aligner.alignment.categorical_slots import align_categorical_slot, foodSlot


customerrating_mapping = {
    'slot': 'rating',
    'values': {
        'low': 'poor',
        'average': 'average',
        'high': 'excellent',
        '1 out of 5': 'poor',
        '3 out of 5': 'average',
        '5 out of 5': 'excellent'
    }
}


def dontcare_realization(text, slot, value):
    text = re.sub('\'', '', text.lower())
    text_tok = word_tokenize(text)

    slot_root = reduce_slot_name(slot)
    slot_root_plural = get_plural(slot_root)

    if slot_root in text_tok or slot_root_plural in text_tok or slot in text_tok:
        for x in ['any', 'all', 'vary', 'varying', 'varied', 'various', 'variety', 'different',
                  'unspecified', 'irrelevant', 'unnecessary', 'unknown', 'n/a', 'particular', 'specific', 'priority', 'choosy', 'picky',
                  'regardless', 'disregarding', 'disregard', 'excluding', 'unconcerned', 'matter', 'specification',
                  'concern', 'consideration', 'considerations', 'factoring', 'accounting', 'ignoring']:
            if x in text_tok:
                return True
        for x in ['no preference', 'no predetermined', 'no certain', 'wide range', 'may or may not',
                  'not an issue', 'not a factor', 'not important', 'not considered', 'not considering', 'not concerned',
                  'without a preference', 'without preference', 'without specification', 'without caring', 'without considering',
                  'not have a preference', 'dont have a preference', 'not consider', 'dont consider', 'not mind', 'dont mind',
                  'not caring', 'not care', 'dont care', 'didnt care']:
            if x in text:
                return True
        if ('preference' in text_tok or 'specifics' in text_tok) and ('no' in text_tok):
            return True
    
    return False


def none_realization(text, slot, value):
    text = re.sub('\'', '', text.lower())
    text_tok = word_tokenize(text)
        
    if reduce_slot_name(slot) in text_tok:
        for x in ['information', 'info', 'inform', 'results', 'requirement', 'requirements', 'specification', 'specifications']:
            if x in text_tok and ('no' in text_tok or 'not' in text_tok or 'any' in text_tok):
                return True
    
    return False


def check_delex_slots(slot, delex_slots):
    if delex_slots is None:
        return None

    for delex_slot in delex_slots:
        if slot in delex_slot:
            return delex_slot

    return None


def reduce_slot_name(slot):
    slot = slot.replace('range', '')
    slot = slot.replace('rating', '')
    slot = slot.replace('size', '')

    if slot == 'hasusbport':
        slot = 'usb'
    elif slot == 'hdmiport':
        slot = 'hdmi'
    elif slot == 'powerconsumption':
        slot = 'power'
    elif slot == 'isforbusinesscomputing':
        slot = 'business'

    return slot.lower()


def get_plural(word):
    if word.endswith('y'):
        return re.sub(r'y$', 'ies', word)
    elif word.endswith('e'):
        return re.sub(r'e$', 'es', word)
    else:
        return word + 's'


def get_scalar_slots():
    return {
        'customerrating': {
            'low': 1,
            'average': 2,
            'high': 3,
            '1 out of 5': 1,
            '3 out of 5': 2,
            '5 out of 5': 3
        },
        'pricerange': {
            'high': 1,
            'moderate': 2,
            'cheap': 3,
            'more than £30': 1,
            '£20-25': 2,
            'less than £20': 3
        },
        'familyfriendly': {
            'no': 1,
            'yes': 3
        }
    }


def find_slot_realization(text, text_tok, slot, value_orig, delex_slot_placeholders,
                          soft_align=False, match_name_ref=False):
    pos = -1
    hallucinated_slots = []

    value = re.sub(r'[-/]', ' ', value_orig)

    # TODO: remove auxiliary slots ('da' and '<!.*?>') beforehand
    if slot == 'da':
        pos = 0
    elif re.match(r'<!.*?>', slot):
        pos = 0
    else:
        delex_slot = check_delex_slots(slot, delex_slot_placeholders)
        if delex_slot is not None:
            pos = text.find(delex_slot)
            delex_slot_placeholders.remove(delex_slot)

            # Find hallucinations of the delexed slot
            slot_cnt = text.count(delex_slot)
            if slot_cnt > 1:
                print('HALLUCINATED SLOT:', slot)
                hallucinated_slots.append(slot)
        else:
            # Universal slot values
            if value == 'dontcare':
                if dontcare_realization(text, slot, value):
                    # TODO: get the actual position
                    pos = 0
                    slot_cnt = text.count(reduce_slot_name(slot))
                    if slot_cnt > 1:
                        print('HALLUCINATED SLOT:', slot)
                        hallucinated_slots.append(slot)
            elif value == 'none':
                if none_realization(text, slot, value):
                    # TODO: get the actual position
                    pos = 0
                    slot_cnt = text.count(reduce_slot_name(slot))
                    if slot_cnt > 1:
                        print('HALLUCINATED SLOT:', slot)
                        hallucinated_slots.append(slot)

            elif slot == 'name' and match_name_ref:
                pos = text.find(value)
                if pos < 0:
                    for pronoun in ['it', 'its', 'they', 'their']:
                        _, pos = find_first_in_list(pronoun, text_tok)
                        if pos >= 0:
                            break

            # E2E restaurant dataset slots
            elif slot == 'familyfriendly':
                pos = align_boolean_slot(text, text_tok, slot, value)
            elif slot == 'food':
                pos = foodSlot(text, text_tok, value)
            elif slot in ['area', 'eattype']:
                if soft_align:
                    pos = align_categorical_slot(text, text_tok, slot, value,
                                                 mode='first_word')
                else:
                    pos = align_categorical_slot(text, text_tok, slot, value,
                                                 mode='exact_match')
            elif slot == 'pricerange':
                if soft_align:
                    pos = align_scalar_slot(text, text_tok, slot, value,
                                            slot_stem_only=True)
                else:
                    pos = align_scalar_slot(text, text_tok, slot, value,
                                            slot_stem_only=False)
            elif slot == 'customerrating':
                if soft_align:
                    pos = align_scalar_slot(text, text_tok, slot, value,
                                            slot_mapping=customerrating_mapping['slot'],
                                            value_mapping=customerrating_mapping['values'],
                                            slot_stem_only=True)
                else:
                    pos = align_scalar_slot(text, text_tok, slot, value,
                                            slot_mapping=customerrating_mapping['slot'],
                                            value_mapping=customerrating_mapping['values'],
                                            slot_stem_only=False)

            # TV dataset slots
            elif slot == 'type':
                if soft_align:
                    pos = align_categorical_slot(text, text_tok, slot, value,
                                                 mode='first_word')
                else:
                    pos = align_categorical_slot(text, text_tok, slot, value,
                                                 mode='exact_match')
            elif slot == 'hasusbport':
                pos = align_boolean_slot(text, text_tok, slot, value,
                                         true_val='true', false_val='false')
            elif slot in ['screensize', 'price', 'powerconsumption']:
                pos = align_numeric_slot_with_unit(text, text_tok, slot, value)
            elif slot in ['color', 'accessories']:
                if soft_align:
                    pos = align_list_with_conjunctions_slot(text, text_tok, slot, value,
                                                            match_all=False)
                else:
                    pos = align_list_with_conjunctions_slot(text, text_tok, slot, value)

            # Laptop dataset slots
            elif slot in ['weight', 'battery', 'drive', 'dimension']:
                pos = align_numeric_slot_with_unit(text, text_tok, slot, value)
            elif slot in ['design', 'utility']:
                if soft_align:
                    pos = align_list_with_conjunctions_slot(text, text_tok, slot, value,
                                                            match_all=False)
                else:
                    pos = align_list_with_conjunctions_slot(text, text_tok, slot, value)
            elif slot == 'isforbusinesscomputing':
                pos = align_boolean_slot(text, text_tok, slot, value,
                                         true_val='true', false_val='false')

            # Video game dataset slots
            elif slot in ['playerperspective', 'platforms']:
                if soft_align:
                    pos = align_list_slot(text, text_tok, slot, value,
                                          match_all=False, mode='first_word')
                else:
                    pos = align_list_slot(text, text_tok, slot, value,
                                          mode='first_word')
            elif slot == 'genres':
                if soft_align:
                    pos = align_list_slot(text, text_tok, slot, value,
                                          match_all=False, mode='exact_match')
                else:
                    pos = align_list_slot(text, text_tok, slot, value,
                                          mode='exact_match')
            elif slot == 'releaseyear':
                pos = align_year_slot(text, text_tok, slot, value)
            elif slot in ['esrb', 'rating']:
                pos = align_scalar_slot(text, text_tok, slot, value,
                                        slot_stem_only=False)
            elif slot in ['hasmultiplayer', 'availableonsteam', 'haslinuxrelease', 'hasmacrelease']:
                pos = align_boolean_slot(text, text_tok, slot, value)

            # Fall back to finding verbatim slot realization
            elif value in text:
                if len(value) > 4 or ' ' in value:
                    pos = text.find(value)
                else:
                    _, pos = find_first_in_list(value, text_tok)

                # value_cnt = text.count(value)
                # if value_cnt > 1:
                #     print('HALLUCINATED SLOT:', slot, value)
                #     hallucinated_slots.append(slot)

    return pos, hallucinated_slots


def preprocess_utterance(utt):
    utt = re.sub(r'[-_/]', ' ', utt.lower())
    utt_tok = [w.strip('.,!?') if len(w) > 1 else w for w in word_tokenize(utt)]

    return utt, utt_tok


# TODO: use delexed utterances for splitting
def split_content(old_mrs, old_utterances, filename, permute=False):
    """Splits the MRs into multiple MRs with the corresponding individual sentences.
    """

    new_mrs = []
    new_utterances = []
    
    slot_fails = OrderedDict()
    instance_fails = set()
    misses = ['The following samples were removed: ']

    # Prepare checkpoints for tracking the progress
    base = max(int(len(old_mrs) * 0.1), 1)
    checkpoints = [base * i for i in range(1, 11)]

    for i, mr in enumerate(old_mrs):
        slots_found = set()
        slots_to_remove = []

        # Print progress message
        if i in checkpoints:
            cur_state = 10 * i / base
            print('Slot alignment is ' + str(cur_state) + '% done.')

        utt = old_utterances[i]
        utt = re.sub(r'\s+', ' ', utt).strip()
        sents = [sent.lower() for sent in sent_tokenize(utt)]
        new_pair = {sent: OrderedDict() for sent in sents}

        for slot, value_orig in mr.items():
            has_slot = False
            slot_root = slot.rstrip(string.digits)
            value = value_orig.lower()

            # Search for the realization of each slot in each sentence
            for sent, new_slots in new_pair.items():
                sent, sent_tok = preprocess_utterance(sent)

                pos, _ = find_slot_realization(sent, sent_tok, slot_root, value, None, soft_align=True, match_name_ref=True)

                if pos >= 0:
                    new_slots[slot] = value_orig
                    slots_found.add(slot)
                    has_slot = True

            if not has_slot:
                # Record details about the missing slot realization
                misses.append('Couldn\'t find ' + slot + '(' + value_orig + ') - ' + old_utterances[i])
                slots_to_remove.append(slot)
                instance_fails.add(utt)
                if slot not in slot_fails:
                    slot_fails[slot] = 0
                slot_fails[slot] += 1
        else:   # TODO: is it necessary to have the "else" clause?
            # Remove slots (from the original MR) whose realizations were not found
            for slot in slots_to_remove:
                del mr[slot]

            # Keep the original sample, however, omitting the unrealized slots
            new_mrs.append(mr)
            new_utterances.append(utt)
            
            if len(new_pair) > 1:
                for sent, new_slots in new_pair.items():
                    if sent == sents[0]:
                        new_slots['position'] = 'outer'
                    else:
                        new_slots['position'] = 'inner'
                        
                    new_mrs.append(new_slots)
                    new_utterances.append(sent)
                    
            if permute:
                permuteSentCombos(new_pair, new_mrs, new_utterances, max_iter=True)

    # Log the instances in which the aligner did not find the slot
    misses.append('We had these misses from all categories: ' + str(slot_fails.items()))
    misses.append('So we had ' + str(len(instance_fails)) + ' samples with misses out of ' + str(len(old_utterances)))
    with io.open(os.path.join(config.SLOT_ALIGNER_DIR, '_logs', filename), 'w', encoding='utf8') as log_file:
        log_file.write('\n'.join(misses))

    return new_mrs, new_utterances


def score_alignment(utt, mr, scoring="default+over-class"):
    """Scores a delexicalized utterance based on the rate of unrealized and/or hallucinated slots.
    """

    slots_found = set()
    num_slot_halluc = 0

    utt, utt_tok = preprocess_utterance(utt)
    matches = set(re.findall(r'<slot_.*?>', utt))

    for slot, value in mr.items():
        slot_root = slot.rstrip(string.digits)
        value = value.lower()

        pos, hallucinated_slots = find_slot_realization(utt, utt_tok, slot_root, value, matches)

        if pos >= 0:
            slots_found.add(slot)

        num_slot_halluc += len(hallucinated_slots)

    # if scoring == "default":
    #    return len(slots_found) / len(curr_mr)
    # elif scoring == "default+over-class":
    #    return (len(slots_found) / len(curr_mr)) / (len(matches) + 1)

    # if scoring == "default":
    #    return len(slots_found) / len(curr_mr)
    # elif scoring == "default+over-class":
    #    return (len(slots_found) - len(matches) + 1) / (len(curr_mr) + 1)

    if scoring == "default":
        return 1 / (len(mr) - len(slots_found) + num_slot_halluc + 1)
    elif scoring == "default+over-class":
        return 1 / (len(mr) - len(slots_found) + num_slot_halluc + 1) / (len(matches) + 1)


def count_errors(utt, mr):
    """Counts unrealized and hallucinated slots in a lexicalized utterance.
    """

    non_categorical_slots = ['familyfriendly', 'pricerange', 'customerrating',
                             'rating', 'hasmultiplayer', 'availableonsteam', 'haslinuxrelease', 'hasmacrelease']

    slots_found = set()
    num_slot_halluc = 0

    utt, utt_tok = preprocess_utterance(utt)
    matches = set(re.findall(r'<slot_.*?>', utt))

    for slot, value in mr.items():
        slot_root = slot.rstrip(string.digits)
        value = value.lower()

        pos, hallucinated_slots = find_slot_realization(utt, utt_tok, slot_root, value, matches)

        if pos >= 0:
            slots_found.add(slot)

        num_slot_halluc += len(hallucinated_slots)

    missing_slots = []
    for slot in mr:
        if slot not in slots_found:
            missing_slots.append(slot)

    num_erroneous_slots = (len(mr) - len(slots_found)) + num_slot_halluc

    return num_erroneous_slots, missing_slots


def find_alignment(utt, mr):
    """Identifies the realization position of each slot in the utterance.
    """

    alignment = []

    utt, utt_tok = preprocess_utterance(utt)

    for slot, value_orig in mr.items():
        slot_root = slot.rstrip(string.digits)
        value = value_orig.lower()

        pos, _ = find_slot_realization(utt, utt_tok, slot_root, value, None)

        if pos >= 0:
            alignment.append((pos, slot, value_orig))

    # Sort the slot realizations by their position
    alignment.sort(key=lambda x: x[0])

    return alignment


def mergeOrderedDicts(mrs, order=None):
    if order is None:
        order = ['da', 'name', 'eattype', 'food', 'pricerange', 'customerrating', 'area', 'familyfriendly', 'near',
                 'type', 'family', 'hasusbport', 'hdmiport', 'ecorating', 'screensizerange', 'screensize', 'pricerange', 'price', 'audio', 'resolution', 'powerconsumption', 'color', 'accessories', 'count',
                 'processor', 'memory', 'driverange', 'drive', 'batteryrating', 'battery', 'weightrange', 'weight', 'dimension', 'design', 'utility', 'platform', 'isforbusinesscomputing', 'warranty']
    merged_mr = OrderedDict()
    for slot in order:
        for mr in mrs:
            if slot in mr:
                merged_mr[slot] = mr[slot]
                break
    return merged_mr


def mergeEntries(merge_tuples):
    """
    :param merge_tuples: list of (utterance, mr) tuples to merge into one pair
    :return:
    """
    sent = ""
    mr = OrderedDict()
    mrs = []
    for curr_sent, curr_mr in merge_tuples:
        sent += " " + curr_sent
        mrs.append(curr_mr)
    mr = mergeOrderedDicts(mrs)
    return mr, sent


def permuteSentCombos(newPairs, mrs, utterances, max_iter=False, depth=1, assume_root=False):
    """
    :param newPairs: dict of {utterance:mr}
    :param mrs: mrs list - assume it's passed in
    :param utterances: utterance list - assume it's passed in
    :param depth: the depth of the combinations. 1 for example means a root sentence + one follow on.
        For example:
        utterance: a. b. c. d.
        depth 1, root a:
        a. b., a. c., a. d.
        depth 2, root a:
        a. b. c., a. d. c., ...
    :param assume_root: if we assume the first sentence in the list of sentences is the root most sentence, this is true,
        if this is true then we will only consider combinations with the the first sentence being the root.
        Note - a sentence is a "root" if it has the actual name of the restraunt in it. In many cases, there is only
        one root anyways.
    :return:
    """
    if len(newPairs) <= 1:
        return
    roots = []
    children = []
    for sent, new_slots in newPairs.items():
        if "name" in new_slots and new_slots["name"] in sent:
            roots.append((sent, new_slots))
        else:
            children.append((sent, new_slots))
    for root in roots:
        tmp = children + roots
        tmp.remove(root)

        combs = []
        for i in range(1, len(tmp) + 1):
            els = [list(x) for x in itertools.combinations(tmp, i)]
            combs.extend(els)

        if max_iter:
            depth = len(tmp)

        for comb in combs:
            if 0 < len(comb) <= depth:
                new_mr, new_utterance = mergeEntries([root] + comb)
                if "position" in new_mr:
                    del new_mr["position"]
                new_utterance = new_utterance.strip()
                if new_utterance not in utterances:
                    mrs.append(new_mr)
                    utterances.append(new_utterance)

        if assume_root:
            break
    # frivolous return for potential debug
    return utterances, mrs


# ---- UNIT TESTS ----

def testPermute():
    """Tests the permutation function.
    """

    newPairs = {"There is a pizza place named Chucky Cheese.": {"name": "Chucky Cheese"},
                "Chucky Cheese Sucks.": {"name": "Chucky Cheese"},
                "It has a ball pit.": {"b": 1}, "The mascot is a giant mouse.": {"a": 1}}

    utterances, mrs = permuteSentCombos(newPairs, [], [])

    for mr, utt in zip(mrs, utterances):
        print(mr, "---", utt)


# ---- MAIN ----

def main():
    print(foodSlot('There is a coffee shop serving good pasta.', 'Italian'))
    # print(foodSlot('This is a green tree.', 'Italian'))

    # testPermute()


if __name__ == '__main__':
    main()
