# -*- coding: utf-8 -*-

import sys  # TODO: tmp
sys.path.insert(0, '../../../projects/lithoxyl')

from lithoxyl.common import DEBUG, get_level, get_prev_level
from lithoxyl.logger import BaseLogger
from lithoxyl.filters import ThresholdFilter
from lithoxyl.emitters import StreamEmitter
from lithoxyl.formatters import Formatter
from lithoxyl.sinks import SensibleSink, QuantileSink

# idea here is that any codified lessons learned here will be merged
# into lithoxyl as one of the sane/sensible defaults.

OUT_TMPL = '{status_char} {end_local_iso8601} {level_name}: {message} {duration_msecs} ms - {extras}'
BEG_TMPL = '{status_char} {level_name}: {message}'


def debug_callable(func):
    def debugged_callable(*a, **kw):
        import pdb;pdb.set_trace()
        return func(*a, **kw)
    return debugged_callable


class BarnsworthLogger(BaseLogger):
    def __init__(self, name, **kwargs):
        enable_begin = kwargs.pop('enable_begin', True)
        out_min_level = get_level(kwargs.pop('min_level', DEBUG))
        if kwargs:
            raise TypeError('unexpected keyword arguments: %r' % kwargs)
        #exc_filter = debug_callable(ThresholdFilter(exception=0))
        exc_filter = ThresholdFilter(exception=DEBUG)
        exc_formatter = Formatter('!! {exc_type}: {exc_tb_str}')
        exc_emitter = StreamEmitter('stderr')
        exc_sink = SensibleSink(exc_formatter, exc_emitter, [exc_filter])

        event_levels = {'success': out_min_level,
                        'failure': get_prev_level(out_min_level),
                        'exception': get_prev_level(out_min_level, 2)}

        out_filter = ThresholdFilter(**event_levels)
        # TODO: warn_char (requires len on FormatField)
        out_formatter = Formatter(OUT_TMPL)
        out_emitter = StreamEmitter('stdout')
        out_sink = SensibleSink(out_formatter, out_emitter, [out_filter])
        self.quantile_sink = q_sink = QuantileSink()
        sinks = [q_sink, exc_sink, out_sink]
        if enable_begin:
            beg_filter = ThresholdFilter(begin=DEBUG)
            beg_formatter = Formatter(BEG_TMPL)
            beg_sink = SensibleSink(beg_formatter,
                                    out_emitter,
                                    filters=[beg_filter],
                                    on='begin')
            sinks.append(beg_sink)
        super(BarnsworthLogger, self).__init__(name, sinks)


if __name__ == '__main__':
    bl = BarnsworthLogger('test_logger')

    for i in range(5):
        with bl.debug('test_record_%s' % i) as t:
            pass

    with bl.info('test_exception', reraise=False) as te:
        raise ValueError('hm')
