r'''Containing NgramFwBwPerplexityMetric'''

from .metric import MetricBase
from ..models.ngram_language_model import KneserNeyInterpolated
from .._utils import hooks

class NgramFwBwPerplexityMetric(MetricBase):
	r'''Metric for calculating n gram forward perplexity and backward perplexity.

	Arguments:
	    {MetricBase.DATALOADER_ARGUMENTS}
	    ngram (int): order of ngram language model
	    reference_test_list (list): Reference sentences with all vocabs in test data
			are passed to :func:`forward` by ``dataloader.data["test"][self.reference_test_key]``.
		{MetricBase.GEN_KEY_ARGUMENTS}
	'''
	@hooks.hook_metric
	def __init__(self, dataloader, ngram, reference_test_list, gen_key="gen", cpu_count=None):
		super().__init__()
		self.dataloader = dataloader
		self.ngram = ngram
		self.reference_test_list = reference_test_list
		self.gen_key = gen_key
		self.hyps = []
		self.refs = []
		self.cpu_count = cpu_count

	def forward(self, data):
		'''Processing a batch of data.

		Arguments:
			data (dict): A dict at least contains the following keys:

				* data[gen_key] (list or :class:`numpy.ndarray` of `int`):
					Sentences generated by model. Contains end token (eg: ``<eos>``),
					but without start token (eg: ``<go>``).
					Size: `[batch_size, gen_sentence_length]`.
		'''
		gen = data[self.gen_key]
		for gen_sent in gen:
			self.hyps.append(list(self.dataloader.convert_ids_to_tokens(gen_sent, trim=True)))

	@hooks.hook_metric_close
	def close(self):
		'''Return a dict which contains:

			* **fwppl**: fw ppl value.
			* **bwppl**: bw ppl value.
			* **fw-bw-ppl**: Harmonic mean of fw and bw ppl value.
			* **fw-bw-ppl hashvalue**: hash value of reference data.
		'''

		for resp_sent in self.reference_test_list:
			self.refs.append(list(self.dataloader.convert_ids_to_tokens(resp_sent[1:], trim=True)))

		model = KneserNeyInterpolated(self.ngram, \
					self.dataloader.vocab_list[2], self.dataloader.vocab_list[3], \
					self.dataloader.vocab_list[1], cpu_count=self.cpu_count)
		print("training forward")
		model.fit(self.refs)
		print("scoring forward")
		fwppl = model.perplexity(self.hyps)

		model = KneserNeyInterpolated(self.ngram, \
					self.dataloader.vocab_list[2], self.dataloader.vocab_list[3], \
					self.dataloader.vocab_list[1], cpu_count=self.cpu_count)
		print("training backward")
		model.fit(self.hyps)
		print("scoring backward")
		bwppl = model.perplexity(self.refs)

		result = {}
		result["fwppl"] = fwppl
		result["bwppl"] = bwppl
		if fwppl + bwppl > 0:
			result["fw-bw-ppl"] = 2.0 * fwppl * bwppl / (fwppl + bwppl)
		else:
			result["fw-bw-ppl"] = 0

		self._hash_relevant_data(self.refs + [self.ngram])
		result["fw-bw-ppl hashvalue"] = self._hashvalue()
		return result
