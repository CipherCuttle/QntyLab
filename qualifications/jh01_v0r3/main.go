// Isolated JH01 V0R3 offline verifier. Sigstore-Go owns all crypto; this owns only policy.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/sigstore/sigstore-go/pkg/bundle"
	"github.com/sigstore/sigstore-go/pkg/root"
	"github.com/sigstore/sigstore-go/pkg/verify"
	"os"
	"strings"
)

type Policy struct{ Repository, RepositoryID, OwnerID, ReleaseID, Tag, PURL, PackageID, TargetCommit, AssetName, AssetSHA256, PredicateType, SignerURI, TSATimestamp string }

var frozen = Policy{"CipherCuttle/QntyLab", "1317911390", "97258089", "370208366", "qntylab-jh01-v1-persistence-qualification-v0r1-7ad471c", "pkg:github/CipherCuttle/QntyLab@qntylab-jh01-v1-persistence-qualification-v0r1-7ad471c", "1317911390", "7ad471c82c9fa6aef0432f6999e0fce0649d2c55", "github_immutable_release_qualification_v0r1.synthetic.json", "191dfe3693a1e10f6efa8a385ca4c86953798d7e27a6f8e0c08dcbefc99ee4a7", "https://in-toto.io/attestation/release/v0.2", "https://dotcom.releases.github.com", "2026-08-13T20:55:02Z"}

func die(s string) { fmt.Fprintln(os.Stderr, "POLICY_REJECTED:", s); os.Exit(1) }
func main() {
	if len(os.Args) != 4 {
		die("usage: ASSET ROOT_JSONL BUNDLE_JSON")
	}
	asset, rootFile, bundleFile := os.Args[1], os.Args[2], os.Args[3]
	rb, e := os.ReadFile(rootFile)
	if e != nil {
		die(e.Error())
	}
	roots := root.TrustedMaterialCollection{}
	for _, line := range strings.Split(strings.TrimSpace(string(rb)), "\n") {
		r, e := root.NewTrustedRootFromJSON([]byte(line))
		if e != nil {
			die("trusted root: " + e.Error())
		}
		roots = append(roots, r)
	}
	b, e := bundle.LoadJSONFromPath(bundleFile)
	if e != nil {
		die("bundle media/parse: " + e.Error())
	}
	f, e := os.Open(asset)
	if e != nil {
		die(e.Error())
	}
	defer f.Close()
	v, e := verify.NewVerifier(roots, verify.WithObserverTimestamps(1))
	if e != nil {
		die(e.Error())
	}
	// Stage A: no statement/predicate access before this succeeds. RFC3161 observer timestamp is mandatory.
	result, e := v.Verify(b, verify.NewPolicy(verify.WithArtifact(f), verify.WithoutIdentitiesUnsafe()))
	if e != nil {
		die("stage A crypto: " + e.Error())
	}
	if result.Signature == nil || result.Signature.Certificate == nil || result.Signature.Certificate.SubjectAlternativeName != frozen.SignerURI {
		die("signer URI")
	}
	if len(result.VerifiedTimestamps) != 1 || result.VerifiedTimestamps[0].Type != "TimestampAuthority" || result.VerifiedTimestamps[0].Timestamp.UTC().Format("2006-01-02T15:04:05Z") != frozen.TSATimestamp {
		die("verified TSA timestamp")
	}
	// Stage B: the statement belongs to the successfully verified DSSE envelope.
	s := result.Statement
	if s == nil || s.Type != "https://in-toto.io/Statement/v1" || s.PredicateType != frozen.PredicateType {
		die("statement type")
	}
	raw, e := json.Marshal(s.Predicate)
	if e != nil {
		die(e.Error())
	}
	var p map[string]string
	if e = json.Unmarshal(raw, &p); e != nil {
		die("predicate schema")
	}
	for k, w := range map[string]string{"repository": frozen.Repository, "repositoryId": frozen.RepositoryID, "ownerId": frozen.OwnerID, "databaseId": frozen.ReleaseID, "tag": frozen.Tag, "purl": frozen.PURL, "packageId": frozen.PackageID} {
		if p[k] != w {
			die("signed " + k)
		}
	}
	commit, assetSubject := 0, 0
	for _, x := range s.Subject {
		if x.GetName() == frozen.AssetName {
			if x.GetDigest()["sha256"] != frozen.AssetSHA256 {
				die("asset subject digest")
			}
			assetSubject++
		}
		if x.GetUri() == frozen.PURL {
			if x.GetDigest()["sha1"] != frozen.TargetCommit {
				die("commit subject digest")
			}
			commit++
		}
	}
	if commit != 1 || assetSubject != 1 {
		die("ambiguous/missing subjects")
	}
	bytes, e := os.ReadFile(asset)
	if e != nil {
		die(e.Error())
	}
	sum := sha256.Sum256(bytes)
	if hex.EncodeToString(sum[:]) != frozen.AssetSHA256 {
		die("local asset hash")
	}
	fmt.Println(`{"stage_a":"PASS","stage_b":"PASS","signer":"https://dotcom.releases.github.com","tsa":"2026-08-13T20:55:02Z"}`)
}
