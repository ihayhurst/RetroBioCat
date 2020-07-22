import os
import mongoengine as db
import time
from retrobiocat_web.retro.rdchiral.main import rdchiralReaction
from retrobiocat_web.mongo.models.biocatdb_models import EnzymeType
from retrobiocat_web.mongo.models.reaction_models import Reaction
from retrobiocat_web.mongo import default_connection

def get_reactions(include_experimental=False, include_two_step=False):
    if include_experimental == True and include_two_step == True:
        return Reaction.objects()
    else:
        return Reaction.objects(db.Q(experimental=include_experimental) | db.Q(two_step=include_two_step))

def load_rxns(query_result):
    rxns = {}
    for rxn in query_result:
        rxns[rxn.name] = []
        for rxn_string in rxn.smarts:
            rxns[rxn.name].append(rdchiralReaction(rxn_string))
    return rxns

def load_cofactors(query_result):
    reactionEnzymeCofactorDict = {}

    for rxn in query_result:
        reactionEnzymeCofactorDict[rxn.name] = {}

        for enz in rxn.cofactors:
            cofactor_minus = rxn.cofactors[enz]['cofactors_minus']
            cofactor_plus = rxn.cofactors[enz]['cofactors_plus']
            reactionEnzymeCofactorDict[rxn.name][enz] = [cofactor_plus, cofactor_minus]

    return reactionEnzymeCofactorDict

def load_reactions_and_enzymes(query_result):
    reactions = set()
    enzymes = set()
    reaction_enzyme_map = dict()

    for rxn in query_result:
        reactions.add(rxn.name)
        reaction_enzyme_map[rxn.name] = set()
        for enz in rxn.cofactors:
            enzymes.add(enz)
            reaction_enzyme_map[rxn.name].add(enz)
        reaction_enzyme_map[rxn.name] = list(reaction_enzyme_map[rxn.name])

    return list(reactions), list(enzymes), reaction_enzyme_map

def load_rxn_strings(query_result):
    rxns = {}
    for rxn in query_result:
        rxns[rxn.name] = []
        for rxn_string in rxn.smarts:
            rxns[rxn.name].append(rxn_string)
    return rxns

def load_rules_by_type(query_result):
    rules_by_type = {}
    for rxn in query_result:
        rule_type = rxn.type
        if rule_type not in rules_by_type:
            rules_by_type[rule_type] = []
        rules_by_type[rule_type].append(rxn.name)
    return rules_by_type

if __name__ == '__main__':
    default_connection.make_default_connection()

    t0 = time.time()
    query_result = get_reactions()
    rxns = load_rxns(query_result)
    reactionEnzymeCofactorDict = load_cofactors(query_result)
    reactions, enzymes, reaction_enzyme_map = load_reactions_and_enzymes(query_result)
    t1 = time.time()

    print(f"Time to load rules = {round(t1-t0, 3)}")
    print(reactions)
