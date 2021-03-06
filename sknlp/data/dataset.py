from collections import Counter
import os
from typing import Dict, List, Tuple, Sequence, Optional, Callable

from mxnet.gluon.data.dataset import Dataset

from sklearn.preprocessing import MultiLabelBinarizer

from .data import SimpleIndexedRecordIO
from ..vocab import Vocab


class RecordFileDataset(Dataset):
    """
    A dataset wrapper for a ``SimpleIndexedRecordIO`` file.

    Each sample is a string representing the raw content of an record.

    Parameters
    ----------
    filename : ``str``
        Path to ``RecordIO`` file.
    """

    def __init__(self, filename: str) -> None:
        self.idx_file = os.path.splitext(filename)[0] + '.idx'
        self.filename = filename
        self._record = SimpleIndexedRecordIO(self.idx_file, self.filename, 'r')

    def __getitem__(self, idx: int) -> str:
        return self._record.read_idx(idx).decode('utf-8')

    def __len__(self) -> int:
        return len(self._record.positions)


class InMemoryDataset(Dataset):
    """
    A dataset wrapper for lists.
    """

    def __init__(
        self,
        text_list: Sequence[str],
        label_list: Sequence[str],
        *args: Sequence[Sequence[str]]
    ) -> None:
        self._record = [
            '\t'.join(row) for row in zip(text_list, label_list, *args)
        ]

    def __getitem__(self, idx: int) -> str:
        return self._record[idx]

    def __len__(self) -> int:
        return len(self._record)


class NLPDataset:
    """
    实现了基本的NLP预处理, 来预处理``Dataset``.

    Parameters
    ----------
    dataset: Dataset
        数据集
    vocab: gluonnlp.Vocab, optional
        词汇表, 如果为None, 会根据数据集构建
    label2idx: Dict[str, int], optional
        标签2ID表, 如果为None, 会根据数据集构建
    segmenters: Sequence[Callable[[str], List[str]]]
        一组分词器
    max_length: int, optional
        文本截断长度
    """

    def __init__(
        self,
        dataset: Dataset,
        vocab: Optional[Vocab] = None,
        segmenter: Optional[Callable[[str], List[str]]] = None,
        max_length: Optional[int] = 100
    ) -> None:
        self._dataset = dataset
        if segmenter is None:
            self._segmenter = list
        else:
            self._segmenter = segmenter
        self._max_length = max_length

        n_samples = len(dataset)
        token_counter = Counter()
        self._text_lengths: List[int] = []
        for i in range(n_samples):
            row = dataset[i]
            text = self._split_row(row)[0]
            if vocab is None:
                words = self._segmenter(text)
                self._text_lengths.append(len(words))
                token_counter.update(words)
        if vocab is None:
            self._vocab = Vocab(token_counter)
        else:
            self._vocab = vocab

    @property
    def text_lengths(self) -> List[int]:
        if len(self._text_lengths) != len(self):
            self._text_lengths = [len(words) for words in self]
        return self._text_lengths

    def _split_row(self, row: str) -> List[str]:
        return row.split('\t')

    def preprocess_text(self, text: str) -> List[int]:
        return self._vocab[self._segmenter(text[:self._max_length])]

    def preprocess_func(self, text: str, *args) -> List[int]:
        processed_text = self.preprocess_text(text)
        return processed_text

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    def __getitem__(self, idx: int) -> List[int]:
        return self.preprocess_func(*self._split_row(self._dataset[idx]))

    def __len__(self) -> int:
        return len(self._dataset)


class SupervisedNLPDataset(NLPDataset):
    """
    实现了基本的NLP预处理, 来预处理``Dataset``.

    Parameters
    ----------
    dataset: Dataset
        数据集
    vocab: gluonnlp.Vocab, optional
        词汇表, 如果为None, 会根据数据集构建
    label2idx: Dict[str, int], optional
        标签2ID表, 如果为None, 会根据数据集构建
    segmenters: Sequence[Callable[[str], List[str]]]
        一组分词器
    max_length: int, optional
        文本截断长度
    """

    def __init__(
        self,
        dataset: Dataset,
        vocab: Optional[Vocab] = None,
        label2idx: Optional[Dict[str, int]] = None,
        segmenter: Optional[Callable[[str], List[str]]] = None,
        max_length: Optional[int] = 100
    ) -> None:
        self._dataset = dataset
        if segmenter is None:
            self._segmenter = list
        else:
            self._segmenter = segmenter
        self._max_length = max_length

        n_samples = len(dataset)
        token_counter = Counter()
        label_counter = Counter()
        self._text_lengths: List[int] = []
        for i in range(n_samples):
            row = dataset[i]
            text, label = self._split_row(row)[:2]
            if vocab is None:
                words = self._segmenter(text)
                self._text_lengths.append(len(words))
                token_counter.update(words)
            if label2idx is None:
                labels = label.split('|')
                label_counter.update(labels)
        del label_counter['']
        if vocab is None:
            self._vocab = Vocab(token_counter)
        else:
            self._vocab = vocab
        if label2idx is None:
            label_list = list(label_counter.keys())
            label_list.sort()
            self._label2idx = dict(zip(label_list, range(len(label_list))))
        else:
            self._label2idx = label2idx
        self._idx2label = {v: k for k, v in self._label2idx.items()}

    @property
    def text_lengths(self) -> List[int]:
        if len(self._text_lengths) != len(self):
            self._text_lengths = [len(words) for words, label in self]
        return self._text_lengths

    def idx2tokens(self, idx_list: List[int]) -> List[str]:
        return self._vocab.to_tokens(idx_list)

    def preprocess_label(self, label: str) -> List[int]:
        return [self._label2idx[l] for l in label.split('|')]

    def preprocess_func(
        self, text: str, label: str, *args
    ) -> Tuple[List[int], List[int]]:
        processed_text = self.preprocess_text(text)
        processed_label = self.preprocess_label(label)
        return processed_text, processed_label

    def __getitem__(self, idx: int) -> Tuple[List[int], List[int]]:
        return self.preprocess_func(*self._split_row(self._dataset[idx]))


class ClassifyDataset(SupervisedNLPDataset):

    def __init__(
        self,
        dataset: Dataset,
        vocab: Optional[Vocab] = None,
        label2idx: Optional[Dict[str, int]] = None,
        segmenter: Optional[Callable[[str], List[str]]] = None,
        max_length: Optional[int] = 100
    ) -> None:
        super().__init__(
            dataset, vocab=vocab, label2idx=label2idx,
            segmenter=segmenter, max_length=max_length
        )
        self._binarizer = MultiLabelBinarizer([
            self._idx2label[i] for i in range(len(self._label2idx))
        ])

    def preprocess_label(self, label: str) -> List[int]:
        return self._binarizer.fit_transform([label.split('|')])[0].tolist()

    def idx2labels(self, idx_list: List[int]) -> List[str]:
        return [self._idx2label[i] for i in idx_list if i in self._idx2label]


class SequenceTagDataset(SupervisedNLPDataset):

    def preprocess_label(self, label: str) -> List[int]:
        return [
            self._label2idx[l] for l in label.split('|')[:self._max_length]
        ]

    def idx2labels(self, idx_list: List[int]) -> List[str]:
        return [self._idx2label.get(i, 'O') for i in idx_list]


# class _SimpleClassifyDataset(ClassifyDatasetMixin, InMemoryDataset):
#     """
#     A dataset wrapper for `InMemoryDataset` with `NLPDatasetMixin`.

#     Examples
#     ---------
#     >>> ds = _SimpleClassifyDataset(['大叫好', '大家好', '好厉害'], ['1|2', '1|2|3', '3|1'])
#     >>> len(ds)
#     3
#     >>> ds[0]
#     ([5, 7, 4], [2, 1])
#     """

#     def __init__(self, text_list, label_list, vocab=None, label2idx=None,
#                  segmenter=None, max_length=100):
#         super().__init__(text_list=text_list,
#                          label_list=label_list,
#                          vocab=vocab,
#                          label2idx=label2idx,
#                          segmenter=segmenter,
#                          max_length=max_length)


# class _SimpleSequenceTagDataset(SequenceTagDatasetMixin, InMemoryDataset):

#     def __init__(self, text_list, label_list, vocab=None, label2idx=None,
#                  segmenter=None, max_length=100):
#         super().__init__(text_list=text_list,
#                          label_list=label_list,
#                          vocab=vocab,
#                          label2idx=label2idx,
#                          segmenter=segmenter,
#                          max_length=max_length)


DATASET_DIR = 'datasets'


# class MsraDataset(SequenceTagDatasetMixin, RecordFileDataset):

#     DIR = 'msra'

#     def __init__(self, is_train_file=True, vocab=None, label2idx=None,
#                  segmenter=None, max_length=100):
#         filename = 'train.rec' if is_train_file else 'test.rec'
#         super().__init__(filename=os.path.join(DATASET_DIR, self.DIR,
#                                                filename),
#                          vocab=vocab,
#                          label2idx=label2idx,
#                          segmenter=segmenter,
#                          max_length=max_length)


# class WaimaiDataset(ClassifyDatasetMixin, RecordFileDataset):

#     DIR = 'waimai'

#     def __init__(self, is_train_file=True, vocab=None, label2idx=None,
#                  segmenter=None, max_length=100):
#         filename = 'train.rec' if is_train_file else 'test.rec'
#         super().__init__(filename=os.path.join(DATASET_DIR, self.DIR,
#                                                filename),
#                          vocab=vocab,
#                          label2idx=label2idx,
#                          segmenter=segmenter,
#                          max_length=max_length)


# class IntentDataset(ClassifyDatasetMixin, RecordFileDataset):

#     DIR = 'intent'

#     def __init__(self, is_train_file=True, vocab=None, label2idx=None,
#                  segmenter=None, max_length=100):
#         filename = 'train.rec' if is_train_file else 'test.rec'
#         super().__init__(filename=os.path.join(DATASET_DIR, self.DIR,
#                                                filename),
#                          vocab=vocab,
#                          label2idx=label2idx,
#                          segmenter=segmenter,
#                          max_length=max_length)

#     def preprocess_label(self, label):
#         if label == 'nonsense':
#             label = ''
#         return self._binarizer.fit_transform([label.split('|')])[0]
#         .astype(np.float32)


# def load_dataset(dataset, segmenter='jieba'):
#     train_dataset = dataset(True, segmenter=segmenter)
#     test_dataset = dataset(False,
#                            vocab=train_dataset.vocab,
#                            label2idx=train_dataset.label2idx,
#                            segmenter=segmenter)
#     return train_dataset, test_dataset


# def load_msra_dataset(segmenter=None):
#     return load_dataset(MsraDataset, segmenter=segmenter)


# def load_waimai_dataset(segmenter='jieba'):
#     return load_dataset(WaimaiDataset, segmenter=segmenter)


# def load_intent_dataset(segmenter='jieba'):
#     return load_dataset(IntentDataset, segmenter=segmenter)
