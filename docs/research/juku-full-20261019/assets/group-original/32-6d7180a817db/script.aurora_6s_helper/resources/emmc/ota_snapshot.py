"""Read-only userspace reader of Linux persistent dm-snapshot v1 stores."""
import bisect,hashlib,os,struct
class Reader:
 def __init__(self,read_at,extents):
  self.read_at=read_at;self.extents=[];self.ends=[];self.size=0
  for offset,size in extents:
   if offset<0 or size<=0:raise ValueError('Bad extent')
   self.extents.append((self.size,offset,size));self.size+=size;self.ends.append(self.size)
 def read(self,offset,size):
  if offset<0 or size<0 or offset+size>self.size:raise ValueError('Read outside extent mapping')
  result=[]
  while size:
   i=bisect.bisect_right(self.ends,offset);start,physical,length=self.extents[i]
   n=min(size,start+length-offset);chunk=self.read_at(physical+offset-start,n)
   if len(chunk)!=n:raise ValueError('Short source read')
   result.append(chunk);offset+=n;size-=n
  return b''.join(result)
def exceptions(cow,target_size):
 magic,valid,version,sectors=struct.unpack('<4I',cow.read(0,16))
 if (magic,valid,version)!=(0x70416e53,1,1):raise ValueError('Invalid persistent snapshot header')
 chunk=sectors*512
 if chunk!=4096 or cow.size%chunk or target_size%chunk:raise ValueError('Unexpected snapshot chunk geometry')
 count=chunk//16;mapping={};used=set();max_chunks=cow.size//chunk
 for area in range(max_chunks//(count+1)+1):
  location=1+(count+1)*area
  if location>=max_chunks:raise ValueError('No terminating exception record')
  raw=cow.read(location*chunk,chunk)
  for old,new in struct.iter_unpack('<QQ',raw):
   if new==0:return chunk,mapping
   if old>=target_size//chunk or new>=max_chunks or new==0 or new%(count+1)==1:
    raise ValueError('Out-of-range or metadata-overlapping exception')
   if old in mapping or new in used:raise ValueError('Duplicate exception')
   mapping[old]=new;used.add(new)
 raise ValueError('No terminating exception record')
def digest_snapshot(origin,cow,target_size,progress=None):
 chunk,mapping=exceptions(cow,target_size);h=hashlib.sha256();total=target_size//chunk;i=0
 while i<total:
  mapped=i in mapping;start=mapping.get(i,i);j=i+1
  while j<total and j-i<256 and (j in mapping)==mapped and mapping.get(j,j)==start+j-i:j+=1
  h.update((cow if mapped else origin).read(start*chunk,(j-i)*chunk));i=j
  if progress:progress(i*chunk,target_size)
 return {'sha256':h.hexdigest(),'bytes':target_size,'exception_chunks':len(mapping),'origin_chunks':total-len(mapping)}
