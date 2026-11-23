"""Narrow container-header facts for large-attachment ordinary qualification.

Not a demuxer, whole-file validator, release profile, or subtitle/font reader.
Only the continuous Segment prefix through its first Cluster is covered. All
actual reads belong to the caller's one existing RangeBudget and probe lane.
"""
import math
import struct


class UnsupportedLayout(ValueError):
    def __init__(self,reason='LAYOUT_UNSUPPORTED'):
        super().__init__('MATROSKA_HEADER_UNSUPPORTED')
        self.reason=reason


EBML, SEGMENT, CLUSTER = 0x1a45dfa3, 0x18538067, 0x1f43b675
INFO, TRACKS, ATTACHMENTS, CHAPTERS = 0x1549a966, 0x1654ae6b, 0x1941a469, 0x1043a770
SEEKHEAD, CUES, TAGS = 0x114d9b74, 0x1c53bb6b, 0x1254c367
SKIP = {0xec, 0xbf}  # Void / CRC, not timing or track declarations.
CODECS = {'V_MPEG4/ISO/AVC':'h264', 'V_MPEGH/ISO/HEVC':'hevc', 'V_AV1':'av1',
          'V_VP9':'vp9', 'V_VP8':'vp8', 'V_MPEG2':'mpeg2video', 'V_FFV1':'ffv1'}
TRACK_FIELDS = {0xd7,0x73c5,0x83,0xb9,0x88,0x55aa,0x55ab,0x55ac,0x55ad,0x55ae,0x55af,
                0x9c,0x6de7,0x6df8,0x23e383,0x234e7a,0x536e,0x22b59c,0x22b59d,
                0x86,0x63a2,0x258688,0x7446,0x3a9697,0x3b4040,0x26b240,0xaa,
                0x56aa,0x56bb,0x55ee,0xe0,0xe1}
VIDEO_FIELDS = {0x9a,0x9d,0x53b8,0x53c0,0xb0,0xba,0x54aa,0x54bb,0x54cc,0x54dd,
                0x54b0,0x54ba,0x54b2,0x54b3,0x2eb524,0x55b0}


def unsupported(reason='LAYOUT_UNSUPPORTED'):
    raise UnsupportedLayout(reason)


def vint(data, offset, maximum, identifier=False):
    if offset >= len(data) or not data[offset]:
        unsupported()
    width, marker = 1, 0x80
    while not data[offset] & marker:
        width, marker = width+1, marker >> 1
    if width > maximum or offset+width > len(data):
        unsupported()
    raw = int.from_bytes(data[offset:offset+width], 'big')
    value = raw if identifier else raw & ((1 << (7*width))-1)
    if identifier and raw == (1 << (7*width+1))-1:
        unsupported()
    return value, width, not identifier and value == (1 << (7*width))-1


def uint(data):
    if not 1 <= len(data) <= 8:
        unsupported()
    return int.from_bytes(data, 'big')


def floating(data):
    if len(data) not in (4,8):
        unsupported()
    value = struct.unpack('>f' if len(data)==4 else '>d', data)[0]
    if not math.isfinite(value) or value <= 0:
        unsupported()
    return value


class Headers:
    def __init__(self, budget, minimum_attachments):
        self.budget, self.minimum_attachments = budget, minimum_attachments
        self.elements = self.metadata_bytes = self.atoms = 0
        self.initial_requests,self.initial_bytes=budget.requests,budget.count
        self.initial_time=budget.clock()
        self.stage,self.last_element='prefix',None

    def read(self, start, size):
        self.budget.guard()  # Real cancellation/deadline is terminal, not soft fallback.
        if (self.budget.requests-self.initial_requests>=24
                or self.budget.clock()-self.initial_time>=8
                or self.budget.count-self.initial_bytes+size>128*1024):
            unsupported('PREFIX_SCAN_LIMIT')
        if size <= 0 or start < 0 or start+size > self.budget.size:
            unsupported()
        # RangeBudget counts actual bytes/digest/requests; no guessed skipped bytes.
        data = b''.join(self.budget.chunks(start,start+size-1))
        if len(data) != size:
            from bobbi_core.media_probe import ProbeError
            raise ProbeError('TRUNCATED_RANGE')
        return data

    def header(self, offset, bound, segment=False):
        self.budget.guard()
        if offset < 0 or offset >= bound or bound > self.budget.size:
            unsupported()
        prefix = self.read(offset,min(5,bound-offset))
        ident, width, _ = vint(prefix,0,4,True)
        self.last_element=ident
        if width >= len(prefix):
            unsupported()
        first = prefix[width]
        if not first:
            unsupported()
        size_width, marker = 1, 0x80
        while not first & marker:
            size_width, marker = size_width+1, marker >> 1
        if size_width > 8 or offset+width+size_width > bound:
            unsupported()
        needed = width+size_width
        if needed > len(prefix):
            prefix += self.read(offset+len(prefix),needed-len(prefix))
        size, _, unknown = vint(prefix,width,8)
        payload = offset+needed
        if unknown and not (segment and ident==SEGMENT):
            unsupported()
        end = bound if unknown else payload+size
        if end > bound:
            unsupported()
        return ident,payload,end

    def body(self, payload, end, limit):
        size=end-payload
        if size > limit or self.metadata_bytes+size > 192*1024:
            unsupported()
        self.metadata_bytes+=size
        return self.read(payload,size) if size else b''

    def children(self, data, depth=0):
        if depth > 8:
            unsupported()
        offset=0
        while offset<len(data):
            self.budget.guard()
            self.elements+=1
            if self.elements>512:
                unsupported()
            ident,width,_=vint(data,offset,4,True)
            self.last_element=ident
            size,size_width,unknown=vint(data,offset+width,8)
            payload=offset+width+size_width
            end=payload+size
            if unknown or end>len(data):
                unsupported()
            yield ident,data[payload:end]
            offset=end

    def ebml(self,data):
        values={}
        for ident,value in self.children(data):
            if ident in SKIP: continue
            if ident not in {0x4286,0x42f7,0x42f2,0x42f3,0x4282,0x4287,0x4285} or ident in values:
                unsupported()
            values[ident]=value
        if values.get(0x4282)!=b'matroska':
            unsupported()
        for ident,default,maximum in ((0x42f7,1,1),(0x42f2,4,4),(0x42f3,8,8),(0x4285,1,4)):
            value=uint(values[ident]) if ident in values else default
            if not 1<=value<=maximum:
                unsupported()

    def info(self,data):
        values={}
        allowed={0x2ad7b1,0x4489,0x4d80,0x5741,0x7ba9,0x4461,0x73a4,0x7384}
        for ident,value in self.children(data):
            if ident in SKIP: continue
            if ident not in allowed or ident in values:
                unsupported()  # Includes external/linked segments and ChapterTranslate.
            values[ident]=value
        if 0x4489 not in values:
            unsupported()
        scale=uint(values[0x2ad7b1]) if 0x2ad7b1 in values else 1000000
        if not 0<scale<=1000000000:
            unsupported()
        duration=floating(values[0x4489])*scale/1000000000
        if not math.isfinite(duration) or duration<=0:
            unsupported()
        return duration

    def tracks(self,data):
        videos, numbers=[],set()
        count=0
        for ident,entry in self.children(data):
            if ident in SKIP: continue
            if ident!=0xae:
                unsupported()
            count+=1
            if count>128:
                unsupported()
            values={}
            for key,value in self.children(entry,1):
                if key in SKIP: continue
                if key not in TRACK_FIELDS and key!=0x6d80:
                    unsupported('TRACK_FIELD_UNSUPPORTED')
                if key in values:
                    unsupported('TRACK_FIELD_DUPLICATE')
                values[key]=value
            if 0x6d80 in values:
                # Collect the whole entry first; TrackType has no subtitle default.
                summary=self.encoding_diagnostic(values.get(0x83),values[0x6d80])
                encodings=summary['encodings']
                plain_subtitle_zlib=(summary['complete'] and summary['track_type']==17 and len(encodings)==1
                    and all(encodings[0][key]==value for key,value in
                        (('order',0),('scope',1),('type',0),('algorithm',0),('settings_bytes',0),('encryption_present',False))))
                if not plain_subtitle_zlib:
                    self.last_element=0x6d80
                    error=UnsupportedLayout('TRACK_FIELD_UNSUPPORTED')
                    error.encoding=summary
                    raise error
                # This encodes subtitle packets only. No decompression, subtitle
                # readiness, font proof, video fact or media profile is inferred.
            if 0xd7 not in values or 0x83 not in values:
                self.last_element=0xae
                unsupported('TRACK_FIELD_REQUIRED')
            number,kind=uint(values[0xd7]),uint(values[0x83])
            if not 0<number<2**63 or number in numbers or not 1<=kind<=254:
                unsupported()
            numbers.add(number)
            if 0x55ee in values and uint(values[0x55ee])!=0:
                self.last_element=0x55ee
                unsupported('BLOCK_ADDITION_UNSUPPORTED')
            if kind!=1: continue
            if uint(values.get(0xb9,b'\x01'))!=1 or 0x86 not in values or 0xe0 not in values:
                unsupported()
            self.last_element=0x86
            try: codec=CODECS[values[0x86].decode('ascii')]
            except (UnicodeError,KeyError): unsupported('CODEC_UNSUPPORTED')
            dimensions={}
            for key,value in self.children(values[0xe0],2):
                if key in SKIP: continue
                if key not in VIDEO_FIELDS: unsupported('VIDEO_FIELD_UNSUPPORTED')
                if key in dimensions: unsupported('VIDEO_FIELD_DUPLICATE')
                dimensions[key]=value
            if 0xb0 not in dimensions or 0xba not in dimensions:
                unsupported()
            width,height=uint(dimensions[0xb0]),uint(dimensions[0xba])
            if not 1<=width<=16384 or not 1<=height<=16384:
                unsupported()
            videos.append(dict(codec_type='video',codec_name=codec,width=width,height=height))
        if len(videos)!=1:
            unsupported()
        return videos

    def encoding_diagnostic(self,kind_data,data):
        result=dict(complete=False,track_type=None,container_ids=[],encodings=[])
        try:
            kind=uint(kind_data) if kind_data is not None else None
            if kind is None or not 1<=kind<=254:return result
            result['track_type']=kind
            child_count=0
            orders=set()
            for ident,body in self.children(data,2):
                if ident in SKIP:continue
                child_count+=1
                if child_count>32 or len(result['encodings'])>=4:return result
                result['container_ids'].append(ident)
                if ident!=0x6240:return result
                fields={}
                row=dict(order=0,scope=1,type=0,algorithm=None,settings_bytes=0,encryption_present=False,
                    defaulted=['order','scope','type'],child_ids=[])
                result['encodings'].append(row)
                for key,value in self.children(body,3):
                    if key in SKIP:continue
                    child_count+=1
                    if child_count>32:return result
                    row['child_ids'].append(key)
                    if key in fields:return result
                    fields[key]=value
                    if key==0x5035:row['encryption_present']=True
                if set(fields)-{0x5031,0x5032,0x5033,0x5034,0x5035}:return result
                for key,name in ((0x5031,'order'),(0x5032,'scope'),(0x5033,'type')):
                    if key in fields:
                        row[name]=uint(fields[key]);row['defaulted'].remove(name)
                    if not 0<=row[name]<=255:return result
                if row['order'] in orders:return result
                orders.add(row['order'])
                if 0x5034 in fields:
                    row['algorithm']=0
                    row['defaulted'].append('algorithm')
                    compression={}
                    for key,value in self.children(fields[0x5034],4):
                        if key in SKIP:continue
                        child_count+=1
                        if child_count>32:return result
                        row['child_ids'].append(key)
                        if key in compression or key not in {0x4254,0x4255}:return result
                        compression[key]=value
                    if 0x4254 in compression:
                        row['algorithm']=uint(compression[0x4254]);row['defaulted'].remove('algorithm')
                    if not 0<=row['algorithm']<=255:return result
                    row['settings_bytes']=len(compression.get(0x4255,b''))
            result['complete']=bool(result['encodings'])
        except UnsupportedLayout:
            pass
        return result

    def chapters(self,data):
        editions=0
        def atom(value,depth):
            self.atoms+=1
            if self.atoms>256: unsupported()
            seen={}
            for ident,body in self.children(value,depth):
                if ident in SKIP: continue
                if ident==0xb6:
                    atom(body,depth+1)
                    continue
                if ident==0x80:
                    # Display strings/languages cannot change the timeline.
                    for key,_ in self.children(body,depth+1):
                        if key not in SKIP|{0x85,0x437c,0x437d,0x437e}: unsupported()
                    continue
                if ident not in {0x73c4,0x5654,0x91,0x92,0x98,0x4598} or ident in seen:
                    unsupported()  # External segment IDs, processes, tracks, unknown semantics.
                seen[ident]=body
                if ident in {0x98,0x4598} and uint(body) not in (0,1): unsupported()
                if ident==0x73c4: uint(body)
            if 0x91 not in seen: unsupported()
            start=uint(seen[0x91])
            if 0x92 in seen and uint(seen[0x92])<start: unsupported()
        for ident,body in self.children(data):
            if ident in SKIP: continue
            if ident!=0x45b9: unsupported()
            editions+=1
            if editions>16: unsupported()
            seen=set()
            for key,value in self.children(body,1):
                if key in SKIP: continue
                if key==0xb6:
                    atom(value,2)
                    continue
                if key not in {0x45bc,0x45bd,0x45db,0x45dd} or key in seen: unsupported()
                seen.add(key)
                parsed=uint(value)
                if key==0x45dd and parsed!=0: unsupported()
                if key in {0x45bd,0x45db} and parsed not in (0,1): unsupported()
        if not editions: unsupported()

    def seeks(self,data):
        result=[]
        for ident,body in self.children(data):
            if ident in SKIP: continue
            if ident!=0x4dbb: unsupported()
            values={}
            for key,value in self.children(body,1):
                if key in SKIP: continue
                if key not in {0x53ab,0x53ac} or key in values: unsupported()
                values[key]=value
            if set(values)!={0x53ab,0x53ac}: unsupported()
            target,width,unknown=vint(values[0x53ab],0,4,True)
            if width!=len(values[0x53ab]) or unknown: unsupported()
            result.append((target,uint(values[0x53ac])))
            if len(result)>32: unsupported()
        return result

    def inspect(self):
        ident,payload,end=self.header(0,self.budget.size)
        if ident!=EBML: unsupported()
        self.stage='ebml'
        self.ebml(self.body(payload,end,4096))
        self.stage='prefix'
        ident,segment,end=self.header(end,self.budget.size,segment=True)
        if ident!=SEGMENT: unsupported()
        offset,covered,advertised,attachments=segment,{},[],0
        metadata,seekheads={},[]
        for _ in range(64):
            ident,payload,upper=self.header(offset,end)
            if ident in {INFO,TRACKS,CHAPTERS} and ident in covered:
                unsupported()
            covered.setdefault(ident,set()).add(offset)
            if ident==CLUSTER:
                break
            if ident in {INFO,TRACKS,CHAPTERS}:
                metadata[ident]=(payload,upper)
            elif ident==ATTACHMENTS: attachments+=upper-payload
            elif ident==SEEKHEAD:
                seekheads.append((payload,upper))
            elif ident not in SKIP|{CUES,TAGS}: unsupported()
            self.stage='prefix'
            offset=upper
            if offset>=end: unsupported()  # Need the actual first Cluster boundary.
        else: unsupported()
        # Ordinary large MKVs do not pay for complete Tracks/Chapters bodies.
        # First collect only bounded layout headers, and enter the richer
        # narrow grammar only after its large-attachment benefit is proved.
        if INFO not in metadata or TRACKS not in metadata or attachments<self.minimum_attachments:
            self.stage='required_headers'
            unsupported()
        self.stage='seekhead'
        for start,upper in seekheads:
            advertised.extend(self.seeks(self.body(start,upper,8192)))
            if len(advertised)>32:unsupported()
        self.stage='seek_coverage'
        for target,relative in advertised:
            self.last_element=target
            absolute=segment+relative
            if not segment<=absolute<end or target not in {INFO,TRACKS,CHAPTERS,ATTACHMENTS,CUES,TAGS,CLUSTER,SEEKHEAD}:
                unsupported()
            if target not in {CUES,TAGS} and absolute not in covered.get(target,set()):
                unsupported()
        self.stage='info'
        duration=self.info(self.body(*metadata[INFO],8192))
        self.stage='tracks'
        streams=self.tracks(self.body(*metadata[TRACKS],65536))
        if CHAPTERS in metadata:
            self.stage='chapters'
            self.chapters(self.body(*metadata[CHAPTERS],65536))
        self.budget.guard()
        return dict(duration=duration,streams=streams,method='matroska_container_header',
                    coverage='prefix_to_first_cluster',attachments_bytes=attachments,
                    chapters_checked=CHAPTERS in covered)


def inspect_headers(budget,minimum_attachments):
    headers=Headers(budget,minimum_attachments)
    try:
        return headers.inspect()
    except UnsupportedLayout as error:
        error.stage,error.element_id=headers.stage,headers.last_element
        raise
