// Runs the pinned upstream generator itself, using reserved fake subscription nodes.
package main

import (
	"fmt"
	"os"
	"sublink/node/protocol"
)

func main() {
	if len(os.Args) != 3 {
		panic("usage: acl-check template.yaml output.yaml")
	}
	proxies := []protocol.Proxy{
		{Name: "fixture-alpha", Type: "ss", Server: "192.0.2.1", Port: 443, Cipher: "aes-128-gcm", Password: "fixture-only"},
		{Name: "fixture-beta", Type: "ss", Server: "192.0.2.2", Port: 443, Cipher: "aes-128-gcm", Password: "fixture-only"},
	}
	data, err := protocol.DecodeClash(proxies, os.Args[1])
	if err != nil {
		panic(err)
	}
	if err := os.WriteFile(os.Args[2], data, 0600); err != nil {
		panic(err)
	}
	fmt.Println("Real SublinkPro DecodeClash wrote:", os.Args[2])
}
