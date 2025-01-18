rsync -avz *.yml root@autothrottle-1:test/
ssh root@autothrottle-1 kubectl apply -f test/

