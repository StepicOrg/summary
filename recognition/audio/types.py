from typing import NamedTuple

RecognizedChunk = NamedTuple('RecognizedChunk', [('start', float), ('end', float), ('text', str)])
