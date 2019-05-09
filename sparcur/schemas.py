import copy
import json
import jsonschema

# FIXME these imports should not be here types rules should be set in another way
from pathlib import Path
import rdflib
from pyontutils.core import OntId, OntTerm
from pysercomb.pyr.units import Expr
from sparcur.core import JEncode


def _format_jsonschema_error(error):
    """Format a :py:class:`jsonschema.ValidationError` as a string."""
    if error.path:
        dotted_path = ".".join([str(c) for c in error.path])
        return "{path}: {message}".format(path=dotted_path, message=error.message)
    return error.message


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors

    def __repr__(self):
        msg = ', '.join([_format_jsonschema_error(e) for e in self.errors])
        return self.__class__.__name__ + f'({msg})'

    def __str__(self):
        return repr(self)

    def json(self):
        """ update this to change how errors appear in the validation pipeline """
        skip = 'schema', 'instance', 'context'  # have to skip context because it has unserializable content
        return [{k:v if k not in skip else k + ' REMOVED'
                 for k, v in e._contents().items()
                 # TODO see if it makes sense to drop these because the parser did know ...
                 if v and k not in skip}
                for e in self.errors]


class ConvertingChecker(jsonschema.FormatChecker):
    _enc = JEncode()

    def check(self, instance, format):
        converted = _enc.default(instance)
        return super().check(converted, format)

class JSONSchema(object):

    schema = {}

    def __init__(self):
        format_checker = jsonschema.FormatChecker()
        #format_checker = ConvertingChecker()
        types = dict(array=(list, tuple),
                     string=(str,
                             Path,
                             rdflib.URIRef,
                             rdflib.Literal,
                             OntId,
                             OntTerm,
                             Expr,))
        self.validator = jsonschema.Draft6Validator(self.schema,
                                                    format_checker=format_checker,
                                                    types=types)

    def validate_strict(self, data):
        # Take a copy to ensure we don't modify what we were passed.
        #appstruct = copy.deepcopy(data)

        appstruct = json.loads(json.dumps(data, cls=JEncode))  # FIXME figure out converters ...

        errors = list(self.validator.iter_errors(appstruct))
        if errors:
            raise ValidationError(errors)

        return appstruct

    def validate(self, data):
        """ capture errors """
        try:
            ok = self.validate_strict(data)  # validate {} to get better error messages
            return True, ok, data  # FIXME better format

        except ValidationError as e:
            return False, e, data  # FIXME better format

    @property
    def total_possible_errors(self):
        # TODO the structure for actual_errors is where we have to recurse
        # this could be applied recursivley now, though using it requires unpacking the output
        total_possible_errors = 0
        if self.schema['type'] == 'object':
            if 'required' in self.schema:
                required = self.schema['required']
            else:
                required = []

            total_possible_errors += len(required)

            # this makes each error matter less the more values you have
            # 
            #for prop, value in self.schema['properties'].items():
                #if prop not in required and len(value) > 1 and prop in instance:

            if 'additionalProperties' in self.schema and not self.schema['additionalProperties']:
                total_possible_errors += 1

        elif self.schema['type'] == 'array' and 'contains' in schema:
            total_possible_errors += 1

        return total_possible_errors
    
        # optional fields means that the total
        # possible errors cannot be known until runtime
        # but what that means is that we assume that optional fields
        # should always be correct and thus that only the static
        # information in the schema will be used to generate the score
        # FIXME the above doesn't actually work because missing optional
        # fields do need to be added at runtime, we'll do that next time


metadata_filename_pattern = r'^[a-z_\/]+\.(xlsx|csv|tsv|json)$'

simple_url_pattern = r'^(https?):\/\/([^\s\/]+)\/([^\s]*)'


class ErrorSchema(JSONSchema):
    schema = {'type':'array',
              'minItems': 1,
              'items': {'type': 'object'},}


class DatasetStructureSchema(JSONSchema):
    schema = {'type': 'object',
              'required': ['submission_file', 'dataset_description_file', 'subjects_file'],
              'properties': {'submission_file': {'type': 'string',
                                                 'pattern': metadata_filename_pattern},
                             'dataset_description_file': {'type': 'string',
                                                          'pattern': metadata_filename_pattern},
                             'subjects_file': {'type': 'string',
                                               'pattern': metadata_filename_pattern},
                             'samples_file': {'type': 'string',
                                              'pattern': metadata_filename_pattern},
                             'dirs': {'type': 'integer',
                                      'minimum': 0},
                             'files': {'type': 'integer',
                                       'minimum': 0},
                             'size': {'type': 'integer',
                                      'minimum': 0},
                             'errors': ErrorSchema.schema,
              }}


class ContributorSchema(JSONSchema):
    schema = {'type': 'object',
              'properties': {
                  'name': {'type': 'string'},
                  'first_name': {'type': 'string'},
                  'last_name': {'type': 'string'},
                  'contributor_orcid_id': {'type': 'string',
                                           'pattern': ('^https://orcid.org/0000-000(1-[5-9]|2-[0-9]|3-'
                                                       '[0-4])[0-9][0-9][0-9]-[0-9][0-9][0-9]([0-9]|X)$')},
                  'contributor_affiliation': {'type': 'string'},
                  'contributor_role': {
                      'type':'array',
                      'minItems': 1,
                      'items': {
                          'type': 'string',
                          'enum': ['ContactPerson',
                                   'Creator',  # allowed here, moved later
                                   'DataCollector',
                                   'DataCurator',
                                   'DataManager',
                                   'Distributor',
                                   'Editor',
                                   'HostingInstitution',
                                   'PrincipalInvestigator',  # added for sparc map to ProjectLeader probably?
                                   'Producer',
                                   'ProjectLeader',
                                   'ProjectManager',
                                   'ProjectMember',
                                   'RegistrationAgency',
                                   'RegistrationAuthority',
                                   'RelatedPerson',
                                   'Researcher',
                                   'ResearchGroup',
                                   'RightsHolder',
                                   'Sponsor',
                                   'Supervisor',
                                   'WorkPackageLeader',
                                   'Other',]}
                  },
                  'is_contact_person': {'type': 'boolean'},
              }}


class ContributorsSchema(JSONSchema):
    schema = {'type': 'array',
              'contains': {
                  'type': 'object',
                  'required': ['is_contact_person'],
                  'properties': {
                      'is_contact_person': {'type': 'boolean', 'enum': [True]},
                  },
              },
              'items': ContributorSchema.schema,
            }


class ContributorOutSchema(JSONSchema):
    schema = copy.deepcopy(ContributorSchema.schema)
    schema['properties']['contributor_role']['items']['enum'].remove('Creator')


class ContributorsOutSchema(JSONSchema):
    schema = copy.deepcopy(ContributorsSchema.schema)
    schema['items'] = ContributorOutSchema.schema


class CreatorSchema(JSONSchema):
    schema = copy.deepcopy(ContributorSchema.schema)
    schema['properties'].pop('contributor_role')
    schema['properties'].pop('is_contact_person')


class CreatorsSchema(JSONSchema):
    schema = {'type': 'array',
              'minItems': 1,
              'items': CreatorSchema.schema}


class DatasetDescriptionSchema(JSONSchema):
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'required': ['name',
                     'description',
                     'funding',
                     'protocol_url_or_doi',
                     'contributors',
                     'completeness_of_data_set'],
        # TODO dependency to have title for complete if completeness is is not complete?
        'properties': {
            'errors': ErrorSchema.schema,
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'keywords': {'type': 'array', 'items': {'type': 'string'}},
            'acknowledgements': {'type': 'string'},
            'funding': {'type': 'string'},
            'completeness_of_data_set': {'type': 'string'},
            'prior_batch_number': {'type': 'string'},
            'title_for_complete_data_set': {'type': 'string'},
            'originating_article_doi': {'type': 'array', 'items': {'type': 'string'}},  # TODO doi matching? maybe types?
            'protocol_url_or_doi': {
                'type': 'array',
                'minItems': 1,
                'items': {'type': 'string',
                          'pattern': simple_url_pattern}},
            'links': {
                'type': 'array',
                'minItems': 1,
                'items': {
                    'type': 'object',
                    'properties': {
                        'additional_links': {'type': 'string'},
                        'link_description': {'type': 'string'},  # FIXME only if there is an additional link? some using for protocol desc
                    }
                }
            },
            'examples': {
                'type': 'array',
                'minItems': 1,   # this pattern makes things self describing
                'items': {
                    'type': 'object',
                    'properties': {
                        'example_image_filename': {'type': 'string'},
                        'example_image_locator': {'type': 'string'},
                        'example_image_description': {'type': 'string'},
                    }
                }
            },
            'contributors': ContributorsSchema.schema
        }
    }


class SubmissionSchema(JSONSchema):
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'errors': ErrorSchema.schema,
            'submission': {
                'type': 'object',
                'required': ['sparc_award_number', 'milestone_achieved', 'milestone_completion_date'],
                # TODO allOf?
                'properties': {'sparc_award_number': {'type': 'string'},
                               'milestone_achieved': {'type': 'string'},
                               'milestone_completion_date': {'type': 'string'},}}}}


class UnitSchema(JSONSchema):
    schema = {'oneOf': [{'type': 'string'},
                        {'type': 'object',
                         # TODO enum on the allowed values here
                         'properties': {'type': {'type': 'string'},
                                        'value': {'type': 'number'},
                                        'unit': {'type': 'string'}}}]}


class SubjectsSchema(JSONSchema):
    schema = {
        'type': 'object',
        'required': ['subjects'],
        'properties': {'subjects': {'type': 'array',
                                    'minItems': 1,
                                    'items': {
                                        'type': 'object',
                                        'required': ['subject_id', 'species'],
                                        'properties': {
                                            'subject_id': {'type': 'string'},
                                            'species': {'type': 'string'},
                                            'strain': {'type': 'string'},  # TODO RRID
                                            'sex': {'type': 'string'},  # sex as a variable ?
                                            'mass': UnitSchema.schema,
                                            'weight': UnitSchema.schema,
                                            'age': UnitSchema.schema,
                                            'age_category': {'type': 'string'},  # TODO uberon
                                        },},},

                       'errors': ErrorSchema.schema,
                       'software': {'type': 'array',
                                    'minItems': 1,
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'software_version': {'type': 'string'},
                                            'software_vendor': {'type': 'string'},
                                            'software_url': {'type': 'string'},
                                            'software_rri': {'type': 'string'},
                                        },},}}}


class SamplesFileSchema(JSONSchema):
    schema = {
        'type': 'object',
        'required': ['samples'],
        'properties': {'samples': {'type': 'array',
                                    'minItems': 1,
                                    'items': {
                                        'type': 'object',
                                        'required': ['sample_id', 'subject_id'],
                                        'properties': {
                                            'sample_id': {'type': 'string'},
                                            'subject_id': {'type': 'string'},
                                            'group': {'type': 'string'},  # FIXME required ??

                                            'specimen': {'type': 'string'},  # what are we expecting here?
                                            'specimen_anatomical_location': {'type': 'string'},

                                            'species': {'type': 'string'},
                                            'strain': {'type': 'string'},  # TODO RRID
                                            'RRID_for_strain': {'type': 'string'},  # FIXME why is this in samples and not subjects?
                                            'genotype': {'type': 'string'},

                                            'sex': {'type': 'string'},  # sex as a variable ?

                                            'mass': {'type': 'string'},  # TODO protc -> json
                                            'weight': {'type': 'string'},  # TODO protc -> json

                                            'age': {'type': 'string'},  # TODO protc -> json
                                            'age_category': {'type': 'string'},  # TODO uberon
                                            'age_range_min': {'type': 'string'},
                                            'age_range_max': {'type': 'string'},

                                            'handedness': {'type': 'string'},
                                            'disease': {'type': 'string'},
                                            'reference_atlas': {'type': 'string'},
                                            'protocol_title': {'type': 'string'},
                                            'protocol_url_or_doi': {'type': 'string'},  # protocols_io_location ??

                                            'experimental_log_file_name': {'type': 'string'},
                                        },},},

                       'errors': ErrorSchema.schema,
                       'software': {'type': 'array',
                                    'minItems': 1,
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'software_version': {'type': 'string'},
                                            'software_vendor': {'type': 'string'},
                                            'software_url': {'type': 'string'},
                                            'software_rri': {'type': 'string'},
                                        },},}}}


class MetaOutSchema(JSONSchema):
    __schema = copy.deepcopy(DatasetDescriptionSchema.schema)
    extra_required = ['award_number',
                      'principal_investigator',
                      'species',
                      'organ',
                      'modality',
                      'contributor_count',
                      'uri_human',
                      'uri_api',
                      'files',
                      'dirs',
                      'size',
                      #'subject_count',
                      #'sample_count',
    ]
    __schema['required'].remove('contributors')
    __schema['required'] += extra_required
    __schema['properties'].pop('contributors')
    __schema['properties'].update({
        'errors': ErrorSchema.schema,
        'dirs': {'type': 'integer'},
        'files': {'type': 'integer'},
        'size': {'type': 'integer'},
        'uri_human': {'type': 'string',
                      'pattern': r'^https://app\.blackfynn\.io/N:organization:',  # FIXME proper regex
        },
        'uri_api': {'type': 'string',
                    'pattern': r'^https://api\.blackfynn\.io/(datasets|packages)/',  # FIXME proper regex
        },
        'award_number': {'type': 'string',
                         'pattern': '^OT|^U18',},
        'principal_investigator': {'type': 'string'},
        'protocol_url_or_doi': {'type': 'array',
                                'minItems': 1,
                                'items': {'type': 'string'}},
        'additional_links': {'type': 'array',
                             'minItems': 1,
                             'items': {'type': 'string'}},
        'species': {'type': 'string'},
        'organ': {'type': 'string'},
        'modality': {'type': 'array',
                     'minItems': 1,
                     'items': {
                         'type': 'string',
                     },
        },  # FIXME array?

        # TODO $ref these w/ pointer?
        # in contributor etc?

        'subject_count': {'type': 'integer'},
        'sample_count': {'type': 'integer'},
        'contributor_count': {'type': 'integer'},})

    schema = {'allOf': [__schema,
                        {'oneOf': [
                            {'required': ['subject_count']},  # FIXME extract subjects from samples ?
                            {'required': ['sample_count']}
                        ]}]}

class DatasetOutSchema(JSONSchema):
    """ Schema that adds the id field since investigators shouldn't need to know
        the id to check the integrity of their data. We need it because that is
        a key piece of information that we use to link everything together. """

    __schema = copy.deepcopy(DatasetStructureSchema.schema)
    __schema['required'] = ['id', 'meta', 'contributors']
    __schema['properties'] = {'id': {'type': 'string',  # ye old multiple meta/bf id issue
                                   'pattern': '^N:dataset:'},
                            'meta': MetaOutSchema.schema,
                            'errors': ErrorSchema.schema,
                            'error_index': {'type': 'integer',
                                            'minimum': 0},
                            #'submission_completeness_index': {'type': 'number',
                                                              #'minimum': 0,
                                                              #'maximum': 1,},
                            'contributors': ContributorsOutSchema.schema,
                            'creators': CreatorsSchema.schema,
                            # FIXME subjects_file might make the name overlap clearer
                            'subjects': SubjectsSchema.schema['properties']['subjects'],  # FIXME SubjectsOutSchema
                            'samples': SamplesFileSchema.schema['properties']['samples'],
                            'resources': {'type':'array',
                                          'items': {'type': 'object'},},
                            'protocols': {'type':'array'},
                            'inputs': {'type': 'object',
                                       # TODO do we need errors at this level?
                                       'properties': {'dataset_description_file': DatasetDescriptionSchema.schema,
                                                      'submission_file': SubmissionSchema.schema,
                                                      'subjects_file': SubjectsSchema.schema,},},}

    # FIXME switch to make samples optional since subject_id will always be there even in samples?
    schema = {'allOf': [__schema,
                        {'oneOf': [
                            {'required': ['subjects']},  # FIXME extract subjects from samples ?
                            {'required': ['samples']}
                        ]}]}


class SummarySchema(JSONSchema):
    # TODO add expected counts
    schema = {'type': 'object',
              'required': ['id', 'meta'],
              'properties': {'id': {'type': 'string',
                                    'pattern': '^N:organization:'},
                             'meta': {'type': 'object',
                                      'properties': {'count': {'type': 'integer'},},},
                             'datasets': {'type': 'array',
                                          'minItems': 1,
                                          'items': DatasetOutSchema.schema,},
                             'errors': ErrorSchema.schema,}}


class HeaderSchema(JSONSchema):
    schema = {'type': 'array',
              'items': {'type': 'string'}}


# constraints on MIS classes
class MISSpecimenSchema(JSONSchema):
    schema = {
        'type': 'object',
        'properties': {
            'TEMP:hasAge': {},
            'TEMP:hasAgeCategory': {},  # hasDevelopmentalStage
            'TEMP:hasBiologicalSex': {},  # TEMP because sparc:hasPhenotypicSex
            'TEMP:hasWeight': {},
            'TEMP:hasGenus': {},
            'TEMP:hasSpecies': {},
            'TEMP:hasStrain': {},  # race/ethnicity?
            'TEMP:hasRRID': {},
            'TEMP:hasGeneticVariation': {},

            'sparc:hasBodyMassIndex': {} ,
            'sparc:hasClinicalInformation': {},
            'sparc:hasDiseaseInformation': {},
            'sparc:hasDrugInformation': {},
            'sparc:hasFamilyHistory': {},
            'sparc:hasGender': {},
            'TEMP:hasHandedness': {},
            'TEMP:hasRace': {},
            'TEMP:hasEthnicity': {},
        },
        'oneOf': [
            {'allOf': [
                {'allOf':
                 [{'required': [
                     'TEMP:hasSpecies',
                     'TEMP:hasBiologicalSex',
                     'TEMP:hasWeight',]},
                  {'oneOf': [{'required': ['TEMP:hasAge']},
                             {'required': ['TEMP:hasAgeCategory']}]}]},
                {'oneOf': [
                    {'properties': {'TEMP:hasSpecies': {'enum': ['NCBITaxon:9606']}},
                     'required': [
                         'sparc:hasBodyMassIndex',
                         'sparc:hasClinicalInformation',
                         'sparc:hasDiseaseInformation',
                         'sparc:hasDrugInformation',
                         'sparc:hasFamilyHistory',
                         #'sparc:hasGender',
                         #'TEMP:hasHandedness',
                         'TEMP:hasRace',
                         'TEMP:hasEthnicity',
                     ]},
                    {'allOf': [
                        {'not': {'properties': {'TEMP:hasSpecies': {'enum': ['NCBITaxon:9606']}}}},
                        {'required': [
                            #'TEMP:hasSupplier',
                            #'TEMP:hasStrain',  # RRID? race/ethnicity?
                            'TEMP:hasRRID',
                         ]},
                    ]},
                ]},
            ]},
        ],
    }


class MISDatasetSchema(JSONSchema):
    moves = [  # FIXME this goes somehwere else
        # from datasetoutschema -> mis
        [[''], ['']],
        [[''], ['']],
        [[''], ['']],
        [[''], ['']],
        [[''], ['']],
        [[''], ['']],
        [['resources'], ['']],
        [['meta', 'protocol_url_or_doi'], ['']],
        #[['meta'], ['sparc:Resource']],
        [['subjects'], ['sparc:Specimen']],
        [['contributors'], ['sparc:Researcher']],  # ah the role confusion
    ]
    schema = {'type': 'object',
              'required': ['curies', 'rdf:type'],
              'properties': {
                  'curies': {'type': 'object'},
                  'rdf:type': {'type': 'string',
                               'pattern': 'sparc:Resource'},
                  #'sparc:'
                  'sparc:Specimen': {'type': 'array',
                                     'items': MISSpecimenSchema.schema},
              }
              }


