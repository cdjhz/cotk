r"""
``cotk.dataloader`` provides classes and functions downloading and
loading benchmark data automatically. It reduces your cost preprocessing
data and provide a fair dataset for every model. It also helps you adapt
your model from one dataset to other datasets.
"""

from .tokenizer import Tokenizer, SimpleTokenizer, PretrainedTokenizer
from .vocab import Vocab, GeneralVocab, PretrainedVocab
from .field import Field, Sentence, SentenceDefault, SentenceGPT2, Session
from .context import Context, FieldContext, VocabContext
from .dataloader import Dataloader, LanguageProcessing
from .language_generation import LanguageGeneration, MSCOCO
from .single_turn_dialog import SingleTurnDialog, OpenSubtitles
from .multi_turn_dialog import MultiTurnDialog, SwitchboardCorpus, UbuntuCorpus

__all__ = [ \
	'Tokenizer', 'SimpleTokenizer', 'PretrainedTokenizer', \
	'Vocab', 'GeneralVocab', 'PretrainedVocab', \
	'Field', 'Sentence', 'SentenceDefault', 'SentenceGPT2','Session', \
	'Context', 'FieldContext', 'VocabContext', \
	'Dataloader', 'LanguageProcessing', \
	'LanguageGeneration', 'MSCOCO', \
	'SingleTurnDialog', 'OpenSubtitles', \
]
