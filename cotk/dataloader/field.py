'''A module for field'''
from typing import Optional, List, Union, Iterator, Tuple, Any, Dict
from itertools import chain
import logging
import hashlib

import numpy as np

from .._utils import trim_before_target
from .._utils.metaclass import DocStringInheritor, LoadClassInterface
from .._utils.unordered_hash import UnorderedSha256, dumps
from .tokenizer import SimpleTokenizer, BaseTokenizer, PretrainedTokenizer
from .vocab import BaseVocab, Vocab, PretrainedVocab, SimpleVocab
from .context import FieldContext

class Field(LoadClassInterface, metaclass=DocStringInheritor):
	'''A base class of data field, which specify the format of the dataset.
	See :class:`LanguageProcessingBase` for the usage.

	Notice :class:`Field` object may be shared between different fields, data sets or dataloader.
	Thus it should contain only settings and not data. (Data can be stored by :class:`_FieldContent`.)
	'''

	DEFAULT_VOCAB_FROM = {
		"train": "train",
		"training": "train",
		"dev": "test",
		"development": "test",
		"valid": "test",
		"validation": "test",
		"test": "test",
		"evaluation": "test"
	}
	'''Dict[str, str]:
			Infer the set type (train, test, or extra)
			from the set name. For example, ``DEFAULT_VOCAB_FROM["dev"] == "test"`` means that the words from the "dev" set
			is used for test.
	'''

	def get_vocab(self) -> Optional[BaseVocab]:
		'''Get :class:`BaseVocab` object for the field. None for no :class:`BaseVocab` specified.

		Returns:
			(:class:`BaseVocab` or None): :class:`BaseVocab` of the field.
		'''
		return None

	def get_tokenizer(self) -> Optional[BaseTokenizer]:
		'''Get :class:`BaseTokenizer` object for the field. None for no :class:`BaseTokenizer` specified.

		Returns:
			(:class:`BaseTokenizer` or None): :class:`BaseTokenizer` of the field.
		'''
		return None

	def _create(self, set_name: str) -> "_FieldContent":
		'''Create a :class:`_FieldContent` to store data which have been read.

		Arguments:
			set_name (str): specify the set name for the :class:`_FieldContent`, which may affect the vocab type.

		Returns:
			:class:`_FieldContent`: the created :class:`_FieldContent` object
		'''
		raise NotImplementedError

	def _get_setting_hash(self, vocabs) -> str:
		'''Get setting hash for the field. ``vocabs`` are provided by :class:`LanguageProcessingBase`.
		This function only encode index of vocab, and other settings. It only encode index because
		encode the setting hash of vocabs cannot explain whether a :class:`BaseVocab` is shared between different vocabs or not.

		Arguments:
			vocabs (list): list of :class:`BaseVocab`.

		Returns:
			str: the setting hash of this field.
		'''
		raise NotImplementedError

	def _get_batch(self, name: str, data, indexes: List[int]) -> Dict[str, Any]:
		'''Invoked by :meth:`LanguageProcessingBase.get_batch`, return the data specified by this field.

		Arguments:
			name (str): name of the field.
			data (Any): the object returned by :meth:`_FieldContent.get_data`
		'''
		raise NotImplementedError

class _FieldContent(metaclass=DocStringInheritor):
	'''Store the content data of a field.
		Different from :class:`Field`, it won't be shared between fields or dataloader,
		and it can save data.
	'''
	def __init__(self):
		self._original_data: List[Any] = []
		self._raw_data_hash: str
		self._data_hash: str

	def _get_next(self, dataset: Iterator[str]) -> Tuple[Any, int]:
		'''Read the next element from ``dataset``.

		Arguments:
			dataset (Iterator[str]): An iterator of the data file.

		Returns:
			Tuple[Any, int]: The element, and the number of lines read.

		'''
		raise NotImplementedError

	def read_next(self, dataset: Iterator[str]) -> int:
		'''Read the next element from ``dataloader`` and store the elements.

		Arguments:
			dataset (Iterator[str]): An iterator of the data file.

		Returns:
			int: the number of lines read.
		'''
		if not isinstance(self._original_data, list):
			raise RuntimeError("read_next must be called before get_data")
		sent, lines = self._get_next(dataset)
		if not sent:
			return 0
		self._original_data.append(sent)
		return lines

	def process_before_vocab(self):
		'''This function is called after all elements read, but before building vocabulary.
		'''
		raise NotImplementedError

	def get_data_number(self) -> int:
		'''Get the number of elements.

		Returns:
			int: The elements in this field.
		'''
		return len(self._original_data)

	def get_data(self) -> Any:
		'''Get the data.

		Returns:
			Any: Return the data which will be stored in the :class:`LanguageProcessingBase`.
		'''
		raise NotImplementedError

	def get_raw_data_hash(self) -> str:
		'''Return the raw data hash of this field content.

		Returns:
			str: raw data hash
		'''
		return self._raw_data_hash

	def get_data_hash(self) -> str:
		'''Return raw data hash of this field content.

		Returns:
			str: data hash
		'''
		return self._data_hash

class _SentenceContent(_FieldContent):
	'''Store the content data of :class:`Sentence` field.
		Different from :class:`Field`, it won't be shared between fields or dataloader,
		and it can save data.

	Arguments:
		field (SentenceBase): The corresponding field of this content.
		vocab_from (str): The type of vocab, must be one of ["train", "test", "extra"]
	'''
	def __init__(self, field: "SentenceBase", vocab_from: str):
		self.field = field
		self.vocab_from = vocab_from
		self._tmp_tokenized_data: Any = None
		super().__init__()

	def _get_next(self, dataset: Iterator[str]) -> Tuple[str, int]:
		"""read one line. Note that it may raise StopIteration.

		Args: TODO: fill

		Examples:
			>>> dataset = iter(["I love NLP.\\n", "Yes I do\\n", "I love deep learning\\n"])
			>>> field = Sentence()
			>>> field._get_next(dataset)
			"I love NLP", 1
			>>> field._get_next(dataset)
			"Yes I do", 1
			>>> field._get_next(dataset)
			"I love deep learning", 1
		"""
		return next(dataset).rstrip(), 1

	def process_before_vocab(self):
		raw_data_hash = UnorderedSha256()
		for data in self._original_data:
			raw_data_hash.update_data(dumps(data))
		self._raw_data_hash = raw_data_hash.hexdigest()

		self._tmp_tokenized_data = tokenized_sents = self.field.tokenize_sentences(self._original_data)

		data_hash = UnorderedSha256()
		for tokenized_sent in tokenized_sents:
			data_hash.update_data(dumps(tokenized_sent))
		self._data_hash = data_hash.hexdigest()

		self.field.get_vocab().add_tokens(list(chain(*tokenized_sents)), self.vocab_from)

	def get_data(self):
		# allvocabs
		id_data = self.field.process_sentences(self._tmp_tokenized_data)
		return {"id": id_data, "str": self._original_data}

class SentenceBase(Field):
	'''A field for sentence. This class is the base class of
	:class:`Sentence` and :class:`SentenceGPT2`.
	{INIT_DOCSTRING}
	'''

	INIT_DOCSTRING = '''If any argument is not specified,
	the value will be first retrieved from :class:`FieldContext`. If still ``None``, default
	value will be used.

	Arguments:
		tokenizer (:class:`BaseTokenizer`, str, optional): The tokenizer used for the field. if str, ``SimpleTokenizer(tokenizer)``
			will be used. No default value, KeyError will be raised.
		vocab (:class:`{VOCAB_CLASS}`, optional): The vocabulary used for this field. Sharing this object between different field can
			build vocabulary together. No default value, KeyError will be raised.
		vocab_from (Dict[str, str], optional): Infer the set type (train, test, or extra) from the set name.
			For example, ``DEFAULT_VOCAB_FROM["dev"] == "test"`` means that the words from the "dev" set
			is used for test. Default: :py:attr:`Field.DEFAULT_VOCAB_FROM`.
		max_sent_length (int, optional): Set the maximum length of the sentence. The left tokens are ignored.
			Default: If None, do not cut the sentence.
		convert_to_lower_letter (bool, optional): Convert all the tokens to lower case after tokenization.
			Default: False'''
	VOCAB_CLASS = "BaseVocab"

	def __init__(self, tokenizer: Union[None, BaseTokenizer, str] = None, \
			vocab: Optional[BaseVocab] = None, \
			vocab_from: Optional[Dict[str, str]] = None, \
			max_sent_length: Optional[int] = None, \
			convert_to_lower_letter: Optional[bool] = None):

		with FieldContext.set_parameters(\
				tokenizer=tokenizer,\
				vocab=vocab,\
				vocab_from=vocab_from,\
				max_sent_length=max_sent_length,\
				convert_to_lower_letter=convert_to_lower_letter):
			filled_tokenizer: Union[BaseTokenizer, str] = FieldContext.get("tokenizer", no_default=True)
			self.vocab: BaseVocab = FieldContext.get("vocab", no_default=True)
			self.vocab_from: Dict[str, str] = FieldContext.get("vocab_from", Field.DEFAULT_VOCAB_FROM)
			self.max_sent_length: int = FieldContext.get("max_sent_length", None)
			self.convert_to_lower_letter: bool = FieldContext.get("convert_to_lower_letter", False)

		self.tokenizer: BaseTokenizer
		if isinstance(filled_tokenizer, str):
			self.tokenizer = SimpleTokenizer(filled_tokenizer)
		elif isinstance(filled_tokenizer, BaseTokenizer):
			self.tokenizer = filled_tokenizer
		else:
			raise TypeError("Unknown tokenizer type")

	def _create(self, set_name) -> _SentenceContent:
		try:
			return _SentenceContent(self, self.vocab_from[set_name])
		except KeyError:
			raise KeyError("Unknown set_name %s, do not specify in the vocab_from" % set_name) from None

	def get_tokenizer(self):
		return self.tokenizer

	def get_vocab(self):
		return self.vocab

	def _get_setting_hash(self, vocabs) -> str:
		return hashlib.sha256(dumps(
			[self.__class__.__name__, \
				#tokenizer_id, \
				self.tokenizer.get_setting_hash(), \
				vocabs.index(self.vocab), \
				#self.vocab.get_setting_hash(), \
				self.vocab_from, \
				self.max_sent_length, \
				self.convert_to_lower_letter \
			])).hexdigest()

	def tokenize_sentences(self, sentences: List[str]) -> List[List[str]]:
		'''Tokenize sentences and convert it to lower case if ``convert_to_lower_letter`` is True.

		Arguments:
			sentences (List[str]): The list of sentence to be tokenized.

		Returns:
			List[List[str]]: The tokenized sentences.
		'''
		tokenized_sentences = self.tokenizer.tokenize_sentences(sentences)
		if self.convert_to_lower_letter:
			return [[token.lower() for token in tokens] for tokens in tokenized_sentences]
		else:
			return tokenized_sentences

	def convert_tokens_to_ids(self, tokens: List[str], add_special=False, only_frequent_word=False) -> List[int]:
		'''TODO: fill

		Arguments:
			tokens (List[str]): 
			add_special (bool, optional): . Defaults: False.
			only_frequent_word (bool, optional): . Defaults: False.

		Returns:
			List[int]: 
		'''
		ids = self.vocab.convert_tokens_to_ids(tokens, only_frequent_word=only_frequent_word)
		if add_special:
			ids = self.add_special_to_ids(ids)
		return ids

	def convert_ids_to_tokens(self, ids: List[int], remove_special=True, trim=True) -> List[str]:
		'''TODO: fill

		Arguments:
			ids (List[int]): 
			remove_special (bool, optional): . Defaults: True.
			trim (bool, optional): . Defaults: True.

		Returns:
			List[str]: 
		'''
		return self.vocab.convert_ids_to_tokens(\
				self.remove_special_in_ids(ids, remove_special=remove_special, trim=trim))

	def convert_ids_to_sentence(self, ids: List[int], remove_special=True, trim=True) -> str:
		'''TODO: fill

		Arguments:
			ids (List[int]): 
			remove_special (bool, optional): . Defaults: True.
			trim (bool, optional): . Defaults: True.

		Returns:
			str: 
		'''
		tokens = self.convert_ids_to_tokens(ids, remove_special=remove_special, trim=trim)
		return self.tokenizer.convert_tokens_to_sentence(tokens)

	def add_special_to_ids(self, ids: List[int]) -> List[int]:
		'''TODO:

		Arguments:
			ids (List[int]): 

		Returns:
			List[int]: 
		'''
		raise NotImplementedError

	def remove_special_in_ids(self, ids: List[int], remove_special=True, trim=True) -> List[int]:
		'''TODO:

		Arguments:
			ids (List[int]): 
			remove_special (bool, optional): . Defaults: True.
			trim (bool, optional): . Defaults: True.

		Returns:
			List[int]: 
		'''		
		raise NotImplementedError

	def process_sentences(self, sentences, add_special=True, cut=True, only_frequent_word=False):
		'''TODO:

		Arguments:
			sentences ([type]): 
			add_special (bool, optional): . Defaults: True.
			cut (bool, optional): . Defaults: True.
			only_frequent_word (bool, optional): . Defaults: False.

		Returns:
			[type]: 
		'''
		# sentences: : Union[List[str], List[List[str]]]
		if not sentences:
			raise ValueError("sentences must not be empty.")
		# list of sentences
		if isinstance(sentences[0], str):
			sentences = self.tokenize_sentences(sentences)
		elif not sentences[0]:
			raise ValueError("sentences[0] must not be an empty string.")

		# list of list of str
		sentences = [self.convert_tokens_to_ids(tokens, add_special=add_special, only_frequent_word=only_frequent_word) for tokens in sentences]
		# list of list of id

		if cut:
			before_lengths = [len(sentence) for sentence in sentences]
			sentences = [sentence[:self.max_sent_length] for sentence in sentences]
			after_lengths = [len(sentence) for sentence in sentences]
			if len(sentences) > 1:
				logging.info("max length before cut: %d, cut percent: %.2f%%", \
						max(before_lengths),
						(sum(before_lengths) - sum(after_lengths)) / sum(before_lengths) * 100)
		# sentence cut
		return sentences

	def recover_sentence(self, ids: List[int], remove_special=None, trim=True) -> str:
		'''TODO: fill

		Arguments:
			ids (List[int]): 
			remove_special ([type], optional): . Defaults: None.
			trim (bool, optional): . Defaults: True.

		Returns:
			str: 
		'''
		return self.convert_ids_to_sentence(\
				self.remove_special_in_ids(ids, remove_special=remove_special, trim=trim), trim=False)

	def _get_batch(self, name: str, data: Dict[str, Any], indexes: List[int]) -> Dict[str, Any]:
		'''Invoked by :class:`LanguageProcessingBase`, returned dict will be used for batch.

		Arguments:
			name (str): The name of this field.
			data (Dict[str, Any]): The data format returned by :class:`_SentenceContent`.
			indexes (List[int]): The required index.

		Returns:
			Dict[str, Any]: The dict for batch.
		'''
		raise NotImplementedError

	def trim_in_ids(self, ids: List[int]) -> List[int]:
		'''TODO: fill

		Arguments:
			ids (List[int]): 

		Returns:
			List[int]: 
		'''
		raise NotImplementedError

	def _remove_special_in_ids(self, ids: List[int], go_id: int, eos_id: int) -> List[int]:
		'''Try to remove special token (``go_id`` at the beginning and the ``eos_id`` at the end) in ``ids``.

		Arguments:
			ids (List[int]): the original ids
			go_id (int): go token
			eos_id (int): eos token

		Returns:
			List[int]: the ids with the special token removed.
		'''
		if not ids:
			return ids
		st, ed = 0, None
		if ids[0] == go_id:
			st = 1
		if ids[-1] == eos_id:
			ed = -1
		return ids[st:ed]

class Sentence(SentenceBase):
	'''A field for sentence.
	{INIT_DOCSTRING}
	'''
	INIT_DOCSTRING = SentenceBase.INIT_DOCSTRING
	VOCAB_CLASS = "Vocab"

	def __init__(self, tokenizer: Union[None, BaseTokenizer, str] = None, \
			vocab: Optional[Vocab] = None, \
			vocab_from: Optional[Dict[str, str]] = None, \
			max_sent_length: Optional[int] = None, \
			convert_to_lower_letter: Optional[bool] = None):

		super().__init__(tokenizer=tokenizer, \
				vocab=vocab, vocab_from=vocab_from, max_sent_length=max_sent_length, \
				convert_to_lower_letter=convert_to_lower_letter)

		if not isinstance(self.vocab, Vocab):
			raise ValueError("Sentence only accept Vocab for vocab")
		self.vocab: Vocab

	def add_special_to_ids(self, ids: List[int]) -> List[int]:
		return [self.vocab.go_id] + ids + [self.vocab.eos_id]

	def remove_special_in_ids(self, ids: List[int], remove_special=True, trim=True) -> List[int]:
		if trim:
			ids = self.trim_in_ids(ids)
		if remove_special:
			ids = self._remove_special_in_ids(ids, self.vocab.go_id, self.vocab.eos_id)
		return ids

	def _get_batch(self, name: str, data: Dict[str, Any], indexes: List[int]) -> Dict[str, Any]:
		if not isinstance(self.vocab, Vocab):
			raise RuntimeError("Subclass must override get_batch if self.vocab is not a Vocab.")
		res: Dict[str, Any] = {}
		data_id, data_str = data["id"], data["str"]
		batch_size = len(indexes)
		res[name + "_length"] = np.array([len(data_id[i]) for i in indexes], dtype=int)
		res_sent = res[name] = np.zeros((batch_size, np.max(res[name + "_length"])), dtype=int)
		for i, j in enumerate(indexes):
			sent = data_id[j]
			res_sent[i, :len(sent)] = sent
		res[name + "_allvocabs"] = res_sent.copy()
		res_sent[res_sent >= self.vocab.frequent_vocab_size] = self.vocab.unk_id
		res[name + "_str"] = [data_str[i] for i in indexes]
		return res

	def trim_in_ids(self, ids: List[int]) -> List[int]:
		ids = trim_before_target(list(ids), self.vocab.eos_id)
		idx = len(ids)
		while idx > 0 and ids[idx - 1] == self.vocab.pad_id:
			idx -= 1
		ids = ids[:idx]
		return ids

class SentenceGPT2(SentenceBase):
	'''A field for sentence in the format of GPT2.
	{INIT_DOCSTRING}
	'''
	INIT_DOCSTRING = SentenceBase.INIT_DOCSTRING
	VOCAB_CLASS = "PretrainedVocab"

	def __init__(self, tokenizer: Union[None, BaseTokenizer] = None, \
			vocab: Optional[PretrainedVocab] = None, \
			vocab_from: Optional[Dict[str, str]] = None, \
			max_sent_length: Optional[int] = None, \
			convert_to_lower_letter: Optional[bool] = None):

		super().__init__(tokenizer=tokenizer, \
				vocab=vocab, vocab_from=vocab_from,\
				max_sent_length=max_sent_length, \
				convert_to_lower_letter=convert_to_lower_letter)

		if not isinstance(self.tokenizer, PretrainedTokenizer) or self.tokenizer.get_tokenizer_class() != "GPT2Tokenizer":
			raise ValueError("You have to specify a pretrained tokenizer compatible with gpt2")
		self.inner_tokenizer = self.tokenizer.tokenizer

		if not isinstance(self.vocab, PretrainedVocab):
			raise ValueError("You have to specify a PretrainedVocab for SentenceGPT2 field")
		self.vocab: PretrainedVocab

	def add_special_to_ids(self, ids: List[int]) -> List[int]:
		return [self.vocab.eos_id] + ids + [self.vocab.eos_id]

	def remove_special_in_ids(self, ids: List[int], remove_special=True, trim=True) -> List[int]:
		if trim:
			ids = self.trim_in_ids(ids)
		if remove_special:
			ids = self._remove_special_in_ids(ids, self.vocab.eos_id, self.vocab.eos_id)
		return ids

	def _get_batch(self, name: str, data: Dict[str, Any], indexes: List[int]) -> Dict[str, Any]:
		res: Dict[str, Any] = {}
		data_id, data_str = data["id"], data["str"]
		batch_size = len(indexes)
		res[name + "_length"] = np.array([len(data_id[i]) for i in indexes], dtype=int)
		res_sent = res[name] = np.ones((batch_size, np.max(res[name + "_length"])), dtype=int) * self.vocab.eos_id
		#res_attn = res[name + "_attnmask"] = np.zeros((batch_size, np.max(res[name + "_length"])), dtype=int)
		for i, j in enumerate(indexes):
			sent = data_id[j]
			res_sent[i, :len(sent)] = sent
		#	res_attn[i, :len(sent)] = 1
		res[name + "_allvocabs"] = res_sent.copy()
		res[name + "_str"] = [data_str[i] for i in indexes]
		return res

	def trim_in_ids(self, ids: List[int]) -> List[int]:
		if ids[0] == self.vocab.eos_id:
			ids = [self.vocab.eos_id] + trim_before_target(list(ids[1:]), self.vocab.eos_id)
		else:
			ids = trim_before_target(list(ids), self.vocab.eos_id)
		return ids


#TODO: fix the Session Field, DenseLabel, SparseLabel

class _SessionContent(_FieldContent):
	'''Store the content data of :class:`Session` Field.
		Different from :class:`Field`, it won't be shared between fields or dataloader,
		and it can save data.
	'''
	def __init__(self, field: "Session", vocab_from: str):
		self.field = field
		self.vocab_from = vocab_from
		self._tmp_tokenized_data: Any = None
		super().__init__()

	def _get_next(self, dataset: Iterator[str]) -> Tuple[List[str], int]:
		#TODO: fix the docstring
		r"""read **several(one or more)** elements and returns the next session. The first several non-space elements,
		followed by a '\\n', are regarded as a session. The first element must not be empty string or '\\n'.
		Note that it may raise StopIteration.
		Args:

		Examples:
			>>> dataset = iter(["a\n", "b\n", "\n", "c\n", "d\e", "e\n", '\n'])
			>>> field = Session()
			>>> field.get_next(dataset)
			['a', 'b']
			>>> field.get_next(dataset)
			['c', 'd', 'e']
		"""
		session: List[str] = []
		lineno = 0
		while True:
			try:
				line = next(dataset)
				lineno += 1
				if line == '\n':
					break
				session.append(line.rstrip())
			except StopIteration:
				break
		if not session:
			raise StopIteration
		return session, lineno

	def process_before_vocab(self):
		raw_data_hash = UnorderedSha256()
		for data in self._original_data:
			raw_data_hash.update_data(dumps(data))
		self._raw_data_hash = raw_data_hash.hexdigest()

		#chained_sessions, session_lengths = self._chain_session(self._original_data)
		self._tmp_tokenized_data = tokenized_sessions = self.field.tokenize_sessions(chained_sessions)
		#self._tmp_tokenized_data = self._restore_session(tokenized_sents, session_lengths)

		data_hash = UnorderedSha256()
		for tokenized_data in self._tmp_tokenized_data:
			data_hash.update_data(dumps(tokenized_data))
		self._data_hash = data_hash.hexdigest()

		self.field.get_vocab().add_tokens(list(chain(*chain(*tokenized_sessions))), self.vocab_from)

	def get_data(self) -> List[List[List[int]]]:
		id_data = self.field.process_sessions(self._tmp_tokenized_data)
		return id_data

class Session(Field):

	def __init__(self):
		pass

#TODO: this field read integers, and this is just the label
class DenseLabel(Field):

	def __init__(self):
		pass

#TODO: this field read tokens, and it should be convert to index.
# However, unlike sentence, it only read one token, and do not need special tokens, rare vocabs, or more.
class SparseLabel(Field):

	def __init__(self, vocab: SimpleVocab):
		pass
