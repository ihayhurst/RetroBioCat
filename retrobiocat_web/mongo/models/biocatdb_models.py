import mongoengine as db
from rdkit import Chem

class EnzymeType(db.Document):
    enzyme_type = db.StringField(max_length=120, unique=True, required=True)
    full_name = db.StringField(default='')
    description = db.StringField(default='')
    other_abbreviations = db.ListField(db.StringField())

    def __unicode__(self):
        return self.enzyme_type

    def __str__(self):
        return self.enzyme_type

    meta = {'indexes': ['enzyme_type']}

from retrobiocat_web.mongo.models.user_models import User
from retrobiocat_web.mongo.models.comments import Comment

class Paper(db.Document):
    doi = db.StringField(unique=True)
    short_citation = db.StringField(default='')
    html = db.StringField(default='')
    owner = db.ReferenceField(User)
    added_by = db.ReferenceField(User)
    edits_by = db.ListField(db.ReferenceField(User))

    title = db.StringField(default='')
    authors = db.ListField(db.StringField())
    journal = db.StringField(default='')
    date = db.DateField()

    status = db.StringField(default='')
    tags = db.ListField(db.StringField())
    reviewed = db.BooleanField(default=False)
    reviewed_by = db.ReferenceField(User)
    has_issues = db.BooleanField(default=False)
    comments = db.ListField(db.ReferenceField(Comment, reverse_delete_rule=4))

    def __unicode__(self):
        return self.short_citation

    def __str__(self):
        return self.short_citation

class Sequence(db.Document):
    enzyme_type = db.StringField(max_length=120, required=True)
    enzyme_name = db.StringField(max_length=120, unique=True, required=True)
    other_names = db.ListField(db.StringField())
    n_tag = db.StringField()
    sequence = db.StringField(default='')
    c_tag = db.StringField()
    sequence_unavailable = db.BooleanField(default=False)

    accession = db.StringField(max_length=20, default='')
    other_identifiers = db.ListField(db.StringField(max_length=20))

    structure = db.BooleanField(default=False)
    pdb = db.StringField(default='')
    mutant_of = db.StringField(default='')
    notes = db.StringField(default='')
    bioinformatics_ignore = db.BooleanField(default=False)

    owner = db.ReferenceField(User)
    added_by = db.ReferenceField(User)
    edits_by = db.ListField(db.ReferenceField(User))
    papers = db.ListField(db.ReferenceField(Paper))

    blast = db.DateTimeField()

    def __unicode__(self):
        return self.enzyme_name

    def __str__(self):
        return self.enzyme_name

    meta = {'indexes': ['enzyme_name', 'enzyme_type']}

class Molecule(db.DynamicDocument):
    smiles = db.StringField()
    mol = db.BinaryField()
    #mfp2_2048 = db.StringField()
    #rdfp2_2048 = db.StringField()

    def get_mol(self):
        return Chem.Mol(self.mol)

    meta = {'indexes': ['smiles']}

class Activity(db.Document):
    enzyme_type = db.StringField()
    enzyme_name = db.StringField()
    reaction = db.StringField()
    short_citation = db.StringField()
    html_doi = db.StringField()

    added_by = db.ReferenceField(User)
    added_by_string = db.StringField()
    paper = db.ReferenceField(Paper)
    edits_by = db.ListField(db.ReferenceField(User))

    substrate_1_smiles = db.StringField()
    substrate_2_smiles = db.StringField()
    product_1_smiles = db.StringField()
    cascade_num = db.StringField()

    temperature = db.StringField()
    ph = db.StringField()
    solvent = db.StringField()
    other_conditions = db.StringField()
    notes = db.StringField()
    reaction_vol = db.StringField()
    formulation = db.StringField()
    biocat_conc = db.StringField()

    kcat = db.FloatField()
    km = db.FloatField()
    mw = db.FloatField()

    substrate_1_conc = db.StringField()
    substrate_2_conc = db.StringField()
    specific_activity = db.FloatField()
    conversion = db.FloatField()
    conversion_time = db.FloatField()

    categorical = db.StringField()
    binary = db.BooleanField()

    selectivity = db.StringField()
    auto_generated = db.BooleanField()

class Tag(db.Document):
    seq = db.StringField()
    n_term = db.BooleanField(default=False)
    c_term = db.BooleanField(default=False)

    def __unicode__(self):
        return self.seq

    def __str__(self):
        return self.seq

class UniRef90(db.Document):
    # These fields are shared with Sequence
    enzyme_name = db.StringField()
    sequence = db.StringField()

    enzyme_type = db.ReferenceField(EnzymeType)
    result_of_blasts_for = db.ListField(db.ReferenceField(Sequence))
    seq_match = db.ReferenceField(Sequence)
    blast_round = db.IntField()

    protein_name = db.StringField()
    tax = db.StringField()
    tax_id = db.StringField()

class Alignment(db.Document):
    enzyme_type = db.ReferenceField(EnzymeType)
    proteins = db.ListField(db.GenericReferenceField(choices=[UniRef90, Sequence]), max_length=2)
    identity = db.FloatField()
    coverage = db.FloatField()
    bitscore = db.FloatField()
    alignment_score = db.FloatField()
    e_value = db.FloatField()







